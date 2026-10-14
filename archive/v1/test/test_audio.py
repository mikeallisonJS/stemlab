import numpy as np
import soundfile as sf

from core.audio import compute_peaks, format_time


def test_peaks_shape_and_range(tone_wav):
    peaks = compute_peaks(tone_wav, buckets=200)
    assert peaks.ndim == 2 and peaks.shape[1] == 2
    assert 190 <= len(peaks) <= 210
    assert np.all(peaks[:, 0] <= peaks[:, 1])
    # The tone has an amplitude of 0.5
    assert abs(peaks[:, 1].max() - 0.5) < 0.01
    assert abs(peaks[:, 0].min() + 0.5) < 0.01


def test_peaks_cover_the_whole_file(tmp_path):
    """A click at the very end must show up in the last bucket."""
    data = np.zeros((44100, 2), dtype=np.float32)
    data[-1] = 0.9
    path = tmp_path / "click.wav"
    sf.write(str(path), data, 44100, subtype="FLOAT")
    peaks = compute_peaks(path, buckets=100)
    assert peaks[-1, 1] > 0.8
    assert peaks[:-1, 1].max() == 0


def test_peaks_of_tiny_and_empty_files(tmp_path):
    tiny = tmp_path / "tiny.wav"
    sf.write(str(tiny), np.full((10, 2), 0.25, dtype=np.float32), 44100, subtype="FLOAT")
    assert len(compute_peaks(tiny, buckets=2000)) == 10
    empty = tmp_path / "empty.wav"
    sf.write(str(empty), np.zeros((0, 2), dtype=np.float32), 44100)
    assert compute_peaks(empty).shape == (0, 2)


def test_format_time():
    assert format_time(0) == "0:00"
    assert format_time(65.9) == "1:05"
    assert format_time(3725) == "1:02:05"
    assert format_time(None) == "--:--"
