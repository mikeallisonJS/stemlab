import os

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtMultimedia import QMediaPlayer

from conftest import write_tone
from core import pipeline
from models import registry
from ui import main_window as main_window_module
from ui.drop_area import DropArea
from ui.main_window import Job, MainWindow
from ui.manage_models_dialog import ManageModelsDialog
from ui.model_selection_dialog import ModelSelectionDialog
from ui.results_window import ResultsWindow, stem_title
from ui.settings_dialog import SettingsDialog
from ui.styles.dark_mode import apply_theme


@pytest.fixture
def window(qtbot, settings, fake_model_class, monkeypatch):
    """A main window whose models are fakes that need no installation."""
    models = {}

    def create_model(identifier):
        model = fake_model_class()
        model.identifier = identifier
        models[identifier] = model
        return model

    monkeypatch.setattr(registry, "create_model", create_model)
    window = MainWindow(settings)
    window.test_models = models
    qtbot.addWidget(window)
    window.show()
    yield window
    window.close()


def wait_for_checks(qtbot, window):
    qtbot.waitUntil(lambda: all(job.state != Job.CHECKING for job in window.jobs.values()), timeout=20000)


def process_all(qtbot, window):
    window.process_audio()
    qtbot.waitUntil(lambda: window.worker is None, timeout=30000)


# Main window ------------------------------------------------------------------

def test_window_lists_the_default_model_of_each_family(window):
    texts = [window.model_combo.itemText(i) for i in range(window.model_combo.count())]
    assert texts == [registry.display_name(identifier) for identifier in registry.default_model_ids()]
    assert not window.process_button.isEnabled()
    assert not window.queue_tree.isVisible()


def test_uninstalled_models_are_marked_and_cannot_process(window, qtbot, tone_wav):
    window.current_model.available = False
    window.refresh_model_labels()
    window.update_model_controls()
    window.add_files([str(tone_wav)])
    wait_for_checks(qtbot, window)
    assert window.model_combo.currentText().endswith("(not installed)")
    assert window.install_button.isVisible()
    assert not window.process_button.isEnabled()
    assert "not installed" in window.drop_area.label.text()


def test_files_are_validated_before_processing(window, qtbot, tmp_path, tone_wav):
    not_audio = tmp_path / "broken.mp3"
    not_audio.write_text("definitely not audio")
    window.add_files([str(tone_wav), str(not_audio), str(tone_wav)])
    assert len(window.jobs) == 2, "the same file is only queued once"
    wait_for_checks(qtbot, window)

    states = {os.path.basename(job.path): job.state for job in window.jobs.values()}
    assert states == {"tone.wav": Job.PENDING, "broken.mp3": Job.INVALID}
    assert window.queue_tree.isVisible()
    assert window.process_button.isEnabled()
    assert [job.path for job in window.jobs_to_process()] == [os.path.normpath(str(tone_wav))]


def test_processing_a_single_file_opens_the_results(window, qtbot, tone_wav):
    window.add_files([str(tone_wav)])
    wait_for_checks(qtbot, window)
    process_all(qtbot, window)

    job = next(iter(window.jobs.values()))
    assert job.state == Job.DONE
    assert list(job.result.stems) == ["vocals", "drums"]
    assert "Done" in job.item.text(2)
    assert not window.progress_bar.isVisible()
    assert len(window.results_windows) == 1
    assert not window.process_button.isEnabled(), "nothing is left to process"

    window.results_windows[0].reject()
    assert window.results_windows == []


def test_batch_processing_with_automatic_saving(window, qtbot, tmp_path, settings):
    files = [write_tone(tmp_path / f"track {n}.wav") for n in (1, 2, 3)]
    settings.set("auto_save", True)
    settings.set("output_dir", str(tmp_path / "stems"))
    settings.set("export_format", "flac")
    window.add_files([str(path) for path in files])
    wait_for_checks(qtbot, window)
    assert window.process_button.text() == "Process 3 Files"
    process_all(qtbot, window)

    assert all(job.state == Job.DONE for job in window.jobs.values())
    assert window.results_windows == [], "results only open automatically for a single file"
    assert "3 of 3" in window.status_label.text()
    for n in (1, 2, 3):
        folder = tmp_path / "stems" / f"track {n} [basic]"
        assert sorted(path.name for path in folder.iterdir()) == ["drums.flac", "vocals.flac"]


def test_automatic_saving_defaults_to_the_source_folder(window, qtbot, tmp_path, settings):
    (tmp_path / "music").mkdir()
    source = write_tone(tmp_path / "music" / "song.wav")
    settings.set("auto_save", True)
    settings.set("open_results", False)
    window.add_files([str(source)])
    wait_for_checks(qtbot, window)
    process_all(qtbot, window)
    assert (tmp_path / "music" / "song [basic]" / "vocals.wav").is_file()


def test_failed_files_are_reported_and_can_be_retried(window, qtbot, tone_wav, monkeypatch):
    shown = []
    monkeypatch.setattr(main_window_module.QMessageBox, "critical",
                        lambda *args, **kwargs: shown.append(args[2]))
    window.current_model.model_name = "broken"
    window.add_files([str(tone_wav)])
    wait_for_checks(qtbot, window)
    process_all(qtbot, window)

    job = next(iter(window.jobs.values()))
    assert job.state == Job.FAILED
    assert "broken" in job.error and "broken" in shown[0]
    assert window.results_windows == []

    # Fixing the problem makes the file processable again
    window.current_model.model_name = "basic"
    assert window.process_button.isEnabled()
    process_all(qtbot, window)
    assert job.state == Job.DONE
    window.results_windows[0].reject()


def test_changing_the_model_offers_reprocessing(window, qtbot, tone_wav, settings):
    settings.set("open_results", False)
    window.add_files([str(tone_wav)])
    wait_for_checks(qtbot, window)
    process_all(qtbot, window)
    assert not window.process_button.isEnabled()

    window.two_stems_checkbox.setChecked(True)
    assert window.process_button.isEnabled()
    assert "vocals, no_vocals" in window.stems_label.text()
    process_all(qtbot, window)
    job = next(iter(window.jobs.values()))
    assert list(job.result.stems) == ["vocals", "no_vocals"]

    window.model_combo.setCurrentIndex(1)
    assert window.process_button.isEnabled()


def test_queue_can_be_edited(window, qtbot, tmp_path):
    files = [write_tone(tmp_path / f"{name}.wav") for name in ("a", "b", "c")]
    window.add_files([str(path) for path in files])
    wait_for_checks(qtbot, window)
    window.queue_tree.topLevelItem(1).setSelected(True)
    assert window.remove_files_button.isEnabled()
    window.remove_selected_files()
    assert [os.path.basename(job.path) for job in window.jobs.values()] == ["a.wav", "c.wav"]
    window.clear_queue()
    assert window.jobs == {} and not window.queue_tree.isVisible()


def test_custom_models_are_remembered(window, settings, qtbot, monkeypatch):
    window.add_model("demucs4:htdemucs_ft")
    window.add_model("demucs4:htdemucs_ft")
    assert window.model_combo.count() == len(registry.default_model_ids()) + 1
    assert settings.custom_models() == ["demucs4:htdemucs_ft"]

    window.model_combo.setCurrentIndex(window.model_combo.findData("demucs4:htdemucs_ft"))
    assert window.remove_button.isVisible()
    assert settings.get("last_model") == "demucs4:htdemucs_ft"

    window.remove_models_batch(["demucs4:htdemucs_ft", registry.default_model_ids()[0]])
    assert window.model_combo.count() == len(registry.default_model_ids()), "default models stay"
    assert settings.custom_models() == []
    assert not window.remove_button.isVisible()


def test_window_restores_models_from_settings(qtbot, settings, fake_model_class, monkeypatch):
    monkeypatch.setattr(registry, "create_model", lambda identifier: fake_model_class())
    settings.set("custom_models", ["spleeter:5stems", "gone:model"])
    settings.set("last_model", "spleeter:5stems")
    window = MainWindow(settings)
    qtbot.addWidget(window)
    assert window.current_model_id == "spleeter:5stems"
    assert window.model_combo.findData("gone:model") == -1, "unknown models are dropped silently"
    window.close()


def test_session_files_are_removed_on_close(window, qtbot, tone_wav, settings):
    settings.set("open_results", False)
    window.add_files([str(tone_wav)])
    wait_for_checks(qtbot, window)
    process_all(qtbot, window)
    session = window.session_dir
    assert session.exists()
    window.close()
    assert not session.exists()


# Drop area ----------------------------------------------------------------------

def test_drop_area_recognises_audio_files():
    assert DropArea.is_audio_file("song.MP3")
    assert DropArea.is_audio_file("C:/music/track.flac")
    assert DropArea.is_audio_file("video.mp4")
    assert not DropArea.is_audio_file("notes.txt")
    assert not DropArea.is_audio_file("archive.zip")
    assert not DropArea.is_audio_file("song.mid"), "MIDI files contain no audio"


def test_drop_area_expands_folders(tmp_path):
    (tmp_path / "album" / "disc2").mkdir(parents=True)
    for name in ("album/b.mp3", "album/a.wav", "album/cover.jpg", "album/disc2/c.flac", "single.ogg"):
        (tmp_path / name).write_bytes(b"")
    found = DropArea.collect_audio_files([str(tmp_path / "album"), str(tmp_path / "single.ogg"),
                                          str(tmp_path / "single.ogg"), str(tmp_path / "missing.mp3")])
    assert [os.path.basename(path) for path in found] == ["a.wav", "b.mp3", "c.flac", "single.ogg"]


def test_clicking_the_drop_area_requests_browsing(qtbot):
    area = DropArea()
    qtbot.addWidget(area)
    area.resize(300, 120)
    with qtbot.waitSignal(area.browse_requested, timeout=1000):
        qtbot.mouseClick(area, Qt.MouseButton.LeftButton)


# Results window -----------------------------------------------------------------

@pytest.fixture
def result(tmp_path, fake_model_class):
    session = tmp_path / "session"
    session.mkdir()
    return pipeline.separate_file(fake_model_class(), write_tone(tmp_path / "My Song.wav"), session,
                                  model_label="Fake (basic)")


def test_results_window_shows_mix_and_stems(qtbot, result, settings):
    window = ResultsWindow(None, result, settings)
    qtbot.addWidget(window)
    window.show()
    assert [row.title for row in window.rows] == ["Original mix", "Vocals", "Drums"]
    assert window.rows[0].stem is None and not hasattr(window.rows[0], "save_button")
    assert window.duration_ms == pytest.approx(2000, abs=50)
    assert "My Song" in window.windowTitle()
    qtbot.waitUntil(lambda: all(row.waveform.peaks is not None for row in window.rows), timeout=10000)
    assert len(window.rows[1].waveform.peaks) > 100
    window.reject()


def test_results_window_playback_follows_the_selected_row(qtbot, result, settings):
    window = ResultsWindow(None, result, settings)
    qtbot.addWidget(window)
    window.show()
    window.audio_output.setVolume(0)

    window.seek(window.rows[1], 0.5)
    assert window.current_row is window.rows[1]
    assert window.rows[1].waveform.active and not window.rows[2].waveform.active
    assert window.rows[2].waveform.position == pytest.approx(0.5), "all rows share one position"
    assert window.time_label.text().startswith("0:01")

    window.toggle_playback(window.rows[2])
    assert window.current_row is window.rows[2]
    assert window.pending_position == pytest.approx(1000, abs=50), "switching rows keeps the position"
    window.reject()
    assert window.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState


def test_results_window_saves_all_stems(qtbot, result, settings, tmp_path, monkeypatch):
    window = ResultsWindow(None, result, settings)
    qtbot.addWidget(window)
    window.format_combo.setCurrentIndex(window.format_combo.findData("mp3"))
    assert window.bitrate_combo.isVisibleTo(window)
    assert settings.export_format() == "mp3", "the chosen format is remembered"

    destination = tmp_path / "saved"
    destination.mkdir()
    monkeypatch.setattr("ui.results_window.QFileDialog.getExistingDirectory",
                        lambda *args, **kwargs: str(destination))
    window.save_all_files()
    qtbot.waitUntil(lambda: window.export_worker is None, timeout=30000)

    folder = destination / "My Song [basic]"
    assert sorted(path.name for path in folder.iterdir()) == ["drums.mp3", "vocals.mp3"]
    assert window.open_folder_button.isVisibleTo(window)
    assert settings.get("last_save_dir") == str(destination)
    window.reject()


def test_results_window_saves_a_single_stem(qtbot, result, settings, tmp_path, monkeypatch):
    window = ResultsWindow(None, result, settings)
    qtbot.addWidget(window)
    target = tmp_path / "just vocals.wav"
    monkeypatch.setattr("ui.results_window.QFileDialog.getSaveFileName",
                        lambda *args, **kwargs: (str(target), ""))
    window.save_stem(window.rows[1])
    qtbot.waitUntil(lambda: window.export_worker is None, timeout=30000)
    assert target.is_file()
    window.reject()


def test_stem_titles():
    assert stem_title("vocals") == "Vocals"
    assert stem_title("no_vocals") == "Instrumental (no vocals)"


# Dialogs ----------------------------------------------------------------------

def test_model_selection_dialog_selects_models(qtbot):
    dialog = ModelSelectionDialog(None, "spleeter:4stems")
    qtbot.addWidget(dialog)
    assert dialog.selected_model == "spleeter:4stems"
    assert dialog.select_button.isEnabled()
    assert dialog.tabs.tabText(dialog.tabs.currentIndex()) == "Spleeter"
    assert "vocals, drums, bass, other" in dialog.details_browsers["spleeter"].toPlainText()

    # Switching to a tab without selection disables the button
    dialog.tabs.setCurrentIndex(0)
    assert dialog.selected_model is None and not dialog.select_button.isEnabled()
    dialog.model_lists["demucs4"].setCurrentRow(0)
    assert dialog.selected_model == "demucs4:htdemucs"
    for family_key in registry.FAMILIES:
        for model_name in registry.FAMILIES[family_key].models:
            assert model_name in dialog.get_model_details(family_key, model_name)


def test_manage_models_dialog_lists_backends_and_custom_models(qtbot):
    dialog = ManageModelsDialog(None, ["demucs4:htdemucs_ft"])
    qtbot.addWidget(dialog)
    rows = [dialog.backend_tree.topLevelItem(i) for i in range(dialog.backend_tree.topLevelItemCount())]
    assert [row.text(1) for row in rows] == ["Not installed"] * 4
    assert dialog.install_button.isEnabled() and not dialog.uninstall_button.isEnabled()

    removed = []
    dialog.models_removed.connect(removed.append)
    assert not dialog.remove_button.isEnabled()
    dialog.model_list.item(0).setCheckState(Qt.CheckState.Checked)
    assert dialog.remove_button.isEnabled()
    dialog.remove_selected()
    assert removed == [["demucs4:htdemucs_ft"]]
    assert dialog.model_list.count() == 0
    dialog.done(0)


def test_settings_dialog_stores_changes(qtbot, settings, tmp_path):
    dialog = SettingsDialog(None, settings)
    qtbot.addWidget(dialog)
    assert not dialog.output_dir_edit.isEnabled(), "only used with automatic saving"
    assert not dialog.bitrate_combo.isEnabled(), "WAV has no bitrate"

    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
    dialog.format_combo.setCurrentIndex(dialog.format_combo.findData("mp3"))
    dialog.auto_save_checkbox.setChecked(True)
    dialog.output_dir_edit.setText(str(tmp_path / "new folder"))
    dialog.shifts_spin.setValue(3)
    dialog.device_combo.setCurrentIndex(dialog.device_combo.findData("cpu"))
    assert dialog.bitrate_combo.isEnabled()
    dialog.accept()

    assert settings.theme() == "dark"
    assert settings.export_format() == "mp3"
    assert settings.get("auto_save") is True
    assert (tmp_path / "new folder").is_dir(), "the output folder is created"
    assert settings.processing_options()["demucs_shifts"] == 3
    assert settings.processing_options()["device"] == "cpu"


def test_settings_dialog_restores_defaults(qtbot, settings):
    settings.set("demucs_shifts", 7)
    dialog = SettingsDialog(None, settings)
    qtbot.addWidget(dialog)
    assert dialog.shifts_spin.value() == 7
    dialog.restore_defaults()
    assert dialog.shifts_spin.value() == 1
    dialog.reject()
    assert settings.get("demucs_shifts") == 7, "cancelling keeps the stored settings"


def test_themes_apply(qtbot, qapp):
    assert apply_theme(qapp, "dark") is True
    assert qapp.palette().window().color().lightness() < 80
    assert apply_theme(qapp, "light") is False
    assert qapp.palette().window().color().lightness() > 150


def test_explicit_themes_do_not_follow_the_system(qtbot, qapp):
    from ui.styles.dark_mode import dark_palette, light_palette
    apply_theme(qapp, "light")
    assert qapp.palette().window().color() == light_palette().window().color()
    assert qapp.palette().text().color().lightness() < 80
    apply_theme(qapp, "dark")
    assert qapp.palette().window().color() == dark_palette().window().color()
    apply_theme(qapp, "light")


def test_results_window_shows_file_names_literally(qtbot, result, settings):
    result.title = "I <3 U & <b>friends</b>"
    window = ResultsWindow(None, result, settings)
    qtbot.addWidget(window)
    from PyQt6.QtWidgets import QLabel
    heading = next(label for label in window.findChildren(QLabel) if "friends" in label.text())
    assert "&lt;3" in heading.text() and "<b>friends" not in heading.text()
    window.reject()


def test_waveform_renders_in_both_states(qtbot, tone_wav):
    from ui.waveform import WaveformView
    view = WaveformView(str(tone_wav))
    qtbot.addWidget(view)
    view.resize(400, 80)
    view.show()
    qtbot.waitUntil(lambda: view.peaks is not None, timeout=10000)

    idle = view.grab().toImage()
    view.set_active(True)
    view.set_position(0.5)
    active = view.grab().toImage()
    assert idle != active
    # Left of the playback position is drawn in full color, right of it dimmed
    assert active.pixelColor(100, 40) != active.pixelColor(300, 40)
    low, high = view._column_envelope(400)
    assert len(low) == len(high) == 400 and (low <= high).all()

    # More pixels than audio data must still work
    view.peaks = view.peaks[:10]
    view._cache_key = None
    assert len(view._column_envelope(400)[0]) == 400
    view.grab()
