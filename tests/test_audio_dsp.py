import numpy as np
import pytest
import soundfile as sf
from conftest import write_tone

from stemlab import audio, dsp
from stemlab.ops.ensemble import combine
from stemlab.ops.export import safe_name

# Audio I/O ------------------------------------------------------------------------


def test_load_returns_channels_first_float32(clip):
    data, rate = audio.load(clip)
    assert data.dtype == np.float32 and data.shape == (2, 5 * 44100) and rate == 44100
    assert audio.info(clip) == {"sample_rate": 44100, "channels": 2, "duration": 5.0}


def test_load_converts_rate_and_channels(tmp_path):
    mono = write_tone(tmp_path / "mono.wav", seconds=1.0, sample_rate=22050, channels=1)
    data, rate = audio.load(mono, sample_rate=44100, channels=2)
    assert rate == 44100 and data.shape == (2, 44100)
    assert np.array_equal(data[0], data[1])
    # A 440 Hz tone keeps its level through resampling
    assert np.sqrt(np.mean(data[0, 1000:-1000] ** 2)) == pytest.approx(0.5 / np.sqrt(2), abs=0.005)


def test_load_decodes_other_formats_with_ffmpeg(tmp_path, tone):
    if not audio.find_ffmpeg():
        pytest.skip("FFmpeg is not installed")
    data, rate = audio.load(tone)
    mp3 = audio.write(tmp_path / "tone", data, rate, "mp3", bitrate="192k")
    assert mp3.suffix == ".mp3"
    m4a = tmp_path / "tone.m4a"
    audio._ffmpeg(["-i", str(tone), "-c:a", "aac", str(m4a)], "make a test file")
    decoded, decoded_rate = audio.load(m4a)
    assert decoded_rate == rate and decoded.shape[0] == 2
    assert decoded.shape[1] == pytest.approx(data.shape[1], abs=4096)


def test_load_rejects_what_is_not_audio(tmp_path):
    text = tmp_path / "notes.txt"
    text.write_text("not audio")
    with pytest.raises(audio.AudioError):
        audio.load(text)
    with pytest.raises(audio.AudioError, match="File not found"):
        audio.load(tmp_path / "missing.flac")


@pytest.mark.parametrize(
    "fmt, depth, subtype",
    [
        ("flac", 16, "PCM_16"),
        ("flac", 24, "PCM_24"),
        ("wav", 16, "PCM_16"),
        ("wav", 24, "PCM_24"),
        ("wav", 32, "FLOAT"),
    ],
)
def test_write_formats(tmp_path, clip, fmt, depth, subtype):
    data, rate = audio.load(clip)
    path = audio.write(tmp_path / "out", data, rate, fmt, depth)
    assert path.name == f"out.{fmt}"
    info = sf.info(str(path))
    assert info.subtype == subtype and info.frames == data.shape[1]


def test_write_keeps_dots_in_names_and_clips_integers(tmp_path):
    loud = np.full((2, 100), 1.5, dtype=np.float32)
    path = audio.write(tmp_path / "Mr. Loud", loud, 44100, "wav", 16)
    assert path.name == "Mr. Loud.wav"
    assert sf.read(str(path), dtype="float32")[0].max() <= 1.0
    exact = audio.write(tmp_path / "exact", loud, 44100, "wav", 32)
    assert sf.read(str(exact), dtype="float32")[0].max() == 1.5, "32-bit float keeps samples beyond full scale"
    with pytest.raises(audio.AudioError):
        audio.write(tmp_path / "x", loud, 44100, "ogg")
    with pytest.raises(audio.AudioError):
        audio.write(tmp_path / "x", loud, 44100, "wav", 20)


def test_channel_and_length_helpers():
    stereo = np.arange(8, dtype=np.float32).reshape(2, 4)
    assert audio.to_channels(stereo, 2) is stereo
    assert audio.to_channels(stereo, 1).shape == (1, 4)
    assert audio.to_channels(stereo[:1], 2).shape == (2, 4)
    assert audio.to_channels(np.zeros((6, 4), dtype=np.float32), 2).shape == (2, 4)
    assert audio.match_length(stereo, 2).shape == (2, 2)
    padded = audio.match_length(stereo, 6)
    assert padded.shape == (2, 6) and not padded[:, 4:].any()


def test_safe_names():
    assert safe_name('a/b\\c:d*e?"f<g>h|i') == "a_b_c_d_e__f_g_h_i"
    assert safe_name("trailing. ") == "trailing"
    assert safe_name("...") == "stem"


# DSP ------------------------------------------------------------------------------


def test_stft_round_trip_is_exact():
    rng = np.random.default_rng(0)
    for length in (100, 2048, 44100, 50001):
        signal = rng.standard_normal(length).astype(np.float32) * 0.3
        restored = dsp.istft(dsp.stft(signal), length)
        assert restored.shape == signal.shape
        assert np.allclose(restored, signal, atol=1e-5), length


def test_levels_and_si_sdr():
    t = np.arange(44100) / 44100
    sine = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    assert dsp.rms_db(sine) == pytest.approx(-3.01, abs=0.01)
    assert dsp.peak_db(sine * 0.5) == pytest.approx(-6.02, abs=0.01)
    assert dsp.rms_db(np.zeros(10)) == -120.0

    # A perfect match would be infinite; the score is capped so it stays valid JSON
    assert dsp.si_sdr(sine, sine) == 120.0
    assert dsp.si_sdr(sine * 0.25, sine) == pytest.approx(120.0, abs=0.01), "scale does not matter"
    noisy = sine + 0.1 * np.random.default_rng(1).standard_normal(len(sine)).astype(np.float32)
    assert dsp.si_sdr(noisy, sine) == pytest.approx(17.0, abs=0.5)
    assert dsp.si_sdr(sine, np.zeros_like(sine)) == -120.0
    assert dsp.si_sdr(np.zeros_like(sine), sine) == -120.0
    import json

    for value in (dsp.si_sdr(sine, sine), dsp.si_sdr(sine, np.zeros_like(sine))):
        json.dumps(value, allow_nan=False)


def test_peaks_envelope():
    signal = np.zeros((2, 1000), dtype=np.float32)
    signal[:, 999] = 0.8
    envelope = dsp.peaks(signal, buckets=10)
    assert len(envelope) == 10 and envelope[-1] == [0.0, 0.8] and envelope[0] == [0.0, 0.0]
    assert len(dsp.peaks(np.zeros((2, 5), dtype=np.float32), buckets=2000)) == 5
    assert dsp.peaks(np.zeros((2, 0), dtype=np.float32)) == []


def test_spectrogram_shows_a_tone_at_its_frequency():
    t = np.arange(44100 * 2) / 44100
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    image = dsp.spectrogram_image(np.stack([tone, tone]), 44100, width=300, height=128)
    assert image.shape == (128, 300, 3) and image.dtype == np.uint8
    brightness = image.astype(int).sum(axis=2).mean(axis=1)  # per row, top is high frequency
    row = int(np.argmax(brightness))
    frequency = np.geomspace(30.0, 22050.0, 128)[::-1][row]
    assert frequency == pytest.approx(1000, rel=0.1)

    png = dsp.png_bytes(image)
    assert png.startswith(b"\x89PNG\r\n\x1a\n") and png.endswith(b"IEND\xaeB`\x82")
    assert dsp.spectrogram_image(np.zeros((2, 10), dtype=np.float32), 44100, 50, 20).shape == (20, 50, 3)


def test_combine_methods_pick_as_documented():
    quiet = np.full((1, 8192), 0.1, dtype=np.float32)
    loud = np.full((1, 8192), 0.4, dtype=np.float32)
    assert np.allclose(combine([quiet, loud], "avg"), 0.25)
    assert np.allclose(combine([quiet, loud], "avg", [1, 3]), 0.325)
    assert np.allclose(combine([quiet, loud, loud], "median"), 0.4)
    middle = slice(2048, -2048)
    assert np.allclose(combine([quiet, loud], "max_spec")[:, middle], 0.4, atol=1e-3)
    assert np.allclose(combine([quiet, loud], "min_spec")[:, middle], 0.1, atol=1e-3)
    with pytest.raises(ValueError):
        combine([quiet, loud], "loudest")
