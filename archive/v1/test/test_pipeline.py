import threading

import pytest

from conftest import write_tone
from core import ffmpeg, pipeline
from core.process import ProcessCancelled
from models.base_model import ModelError


def test_sort_stems_uses_display_order():
    assert pipeline.sort_stems(["other", "bass", "vocals", "drums"]) == ["vocals", "drums", "bass", "other"]
    assert pipeline.sort_stems(["no_vocals", "vocals"]) == ["vocals", "no_vocals"]
    assert pipeline.sort_stems(["zebra", "vocals", "alpha"]) == ["vocals", "alpha", "zebra"]


def test_separate_file_produces_result(tmp_path, fake_model_class):
    source = write_tone(tmp_path / "My Song.flac", sample_rate=48000)
    session = tmp_path / "session"
    session.mkdir()
    progress, statuses = [], []
    result = pipeline.separate_file(fake_model_class(), source, session,
                                    progress=progress.append, status=statuses.append,
                                    model_label="Fake Label")

    assert result.title == "My Song"
    assert result.model_label == "Fake Label"
    assert list(result.stems) == ["vocals", "drums"]
    assert all(path.is_file() for path in result.stems.values())
    assert ffmpeg.is_standard_wav(result.mix)
    assert result.directory.parent == session
    assert progress[0] == 0 and progress[-1] == 100 and progress == sorted(progress)
    assert statuses[0] == "Converting audio..."

    result.discard()
    assert not result.directory.exists()


def test_failures_leave_no_working_files(tmp_path, tone_wav, fake_model_class):
    session = tmp_path / "session"
    session.mkdir()
    with pytest.raises(ModelError):
        pipeline.separate_file(fake_model_class("broken"), tone_wav, session)
    with pytest.raises(ffmpeg.AudioError):
        pipeline.separate_file(fake_model_class(), tmp_path / "missing.wav", session)
    text = tmp_path / "notes.mp3"
    text.write_text("not audio")
    with pytest.raises(ffmpeg.AudioError):
        pipeline.separate_file(fake_model_class(), text, session)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ProcessCancelled):
        pipeline.separate_file(fake_model_class(), tone_wav, session, cancel_event=cancel)
    assert list(session.iterdir()) == []


def test_export_result_writes_a_folder_per_track(tmp_path, fake_model_class):
    source = write_tone(tmp_path / "My Song.wav")
    session = tmp_path / "session"
    session.mkdir()
    result = pipeline.separate_file(fake_model_class(), source, session)

    progress = []
    folder = pipeline.export_result(result, tmp_path / "exports", "mp3", "192k", progress=progress.append)
    assert folder.parent == tmp_path / "exports"
    assert folder.name.endswith("[basic]")
    assert sorted(path.name for path in folder.iterdir()) == ["drums.mp3", "vocals.mp3"]
    assert progress == [50, 100]

    # Saving again in another format adds to the same folder
    pipeline.export_result(result, tmp_path / "exports", "wav", "320k")
    assert len(list(folder.iterdir())) == 4


def test_export_folder_name_is_safe_on_every_platform(tmp_path, tone_wav, fake_model_class):
    session = tmp_path / "session"
    session.mkdir()
    result = pipeline.separate_file(fake_model_class(), tone_wav, session)
    result.title = 'What? <A> "Song": Part 1/2 * |'
    name = result.export_folder_name()
    assert not any(character in name for character in '<>:"/\\|?*')
    assert name.endswith("[basic]")


def test_tracks_with_the_same_name_get_separate_folders(tmp_path, fake_model_class):
    session = tmp_path / "session"
    session.mkdir()
    results = []
    for disc in ("disc1", "disc2"):
        (tmp_path / disc).mkdir()
        source = write_tone(tmp_path / disc / "01 Intro.wav")
        results.append(pipeline.separate_file(fake_model_class(), source, session))

    folders = pipeline.ExportFolders()
    exports = tmp_path / "exports"
    first = pipeline.export_result(results[0], exports, "wav", "320k", folders=folders)
    second = pipeline.export_result(results[1], exports, "wav", "320k", folders=folders)
    again = pipeline.export_result(results[0], exports, "wav", "320k", folders=folders)

    assert first.name == "01 Intro [basic]"
    assert second.name == "01 Intro [basic] (2)"
    assert again == first, "saving the same track again reuses its folder"
    assert (first / "vocals.wav").is_file() and (second / "vocals.wav").is_file()
