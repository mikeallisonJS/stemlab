import numpy as np
import pytest
import soundfile as sf

from conftest import write_tone
from core import ffmpeg


def test_ffmpeg_is_available():
    assert ffmpeg.find_ffmpeg()


def test_standard_wav_detection(tmp_path, tone_wav):
    assert ffmpeg.is_standard_wav(tone_wav)
    assert not ffmpeg.is_standard_wav(write_tone(tmp_path / "mono.wav", channels=1))
    assert not ffmpeg.is_standard_wav(write_tone(tmp_path / "48k.wav", sample_rate=48000))
    assert not ffmpeg.is_standard_wav(write_tone(tmp_path / "24bit.wav", subtype="PCM_24"))
    assert not ffmpeg.is_standard_wav(tmp_path / "missing.wav")


def test_convert_mono_low_rate_to_standard_wav(tmp_path):
    source = write_tone(tmp_path / "source.flac", seconds=1.5, sample_rate=22050, channels=1)
    converted = ffmpeg.convert_to_wav(source, tmp_path / "out" / "converted.wav")
    assert ffmpeg.is_standard_wav(converted)
    info = sf.info(str(converted))
    assert info.frames / info.samplerate == pytest.approx(1.5, abs=0.05)


def test_convert_handles_unusual_file_names(tmp_path):
    source = write_tone(tmp_path / "Señor (live) [2024] & friends.wav", sample_rate=48000)
    converted = ffmpeg.convert_to_wav(source, tmp_path / "converted.wav")
    assert ffmpeg.is_standard_wav(converted)


def test_convert_rejects_non_audio(tmp_path):
    text = tmp_path / "notes.txt"
    text.write_text("this is not audio")
    with pytest.raises(ffmpeg.AudioError):
        ffmpeg.convert_to_wav(text, tmp_path / "out.wav")
    with pytest.raises(ffmpeg.AudioError):
        ffmpeg.convert_to_wav(tmp_path / "missing.mp3", tmp_path / "out.wav")


def test_media_duration(tmp_path, tone_wav):
    assert ffmpeg.media_duration(tone_wav) == pytest.approx(2.0, abs=0.01)
    text = tmp_path / "notes.txt"
    text.write_text("this is not audio")
    assert ffmpeg.media_duration(text) is None
    assert ffmpeg.media_duration(tmp_path / "missing.mp3") is None


def test_media_duration_of_compressed_audio(tmp_path, tone_wav):
    """Formats libsndfile cannot read fall back to FFmpeg."""
    m4a = ffmpeg.export_audio(tone_wav, tmp_path / "tone", "m4a", "128k")
    assert ffmpeg.media_duration(m4a) == pytest.approx(2.0, abs=0.2)


@pytest.mark.parametrize("fmt", list(ffmpeg.EXPORT_FORMATS))
def test_export_every_format(tmp_path, tone_wav, fmt):
    exported = ffmpeg.export_audio(tone_wav, tmp_path / "exported" / "stem", fmt, "192k")
    assert exported.suffix == ffmpeg.EXPORT_FORMATS[fmt].extension
    assert exported.stat().st_size > 1000
    assert ffmpeg.media_duration(exported) == pytest.approx(2.0, abs=0.2)


def test_export_keeps_audio_content(tmp_path, tone_wav):
    exported = ffmpeg.export_audio(tone_wav, tmp_path / "stem.flac", "flac")
    original, _ = sf.read(str(tone_wav))
    restored, _ = sf.read(str(exported))
    assert np.allclose(original, restored, atol=1e-4)


def test_export_replaces_extension(tmp_path, tone_wav):
    exported = ffmpeg.export_audio(tone_wav, tmp_path / "stem.wav", "mp3")
    assert exported.name == "stem.mp3"


def test_export_rejects_unknown_format(tmp_path, tone_wav):
    with pytest.raises(ffmpeg.AudioError):
        ffmpeg.export_audio(tone_wav, tmp_path / "stem", "xyz")


def test_export_keeps_dots_that_are_part_of_the_name(tmp_path, tone_wav):
    exported = ffmpeg.export_audio(tone_wav, tmp_path / "Mr. Brightside - vocals", "wav")
    assert exported.name == "Mr. Brightside - vocals.wav"
    exported = ffmpeg.export_audio(tone_wav, tmp_path / "take.v2", "flac")
    assert exported.name == "take.v2.flac"
    exported = ffmpeg.export_audio(tone_wav, tmp_path / "Song.WAV", "mp3")
    assert exported.name == "Song.mp3"
