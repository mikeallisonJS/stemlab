"""
Tests that run the real separation models.

They are skipped unless CAPTAINSTEMS_INTEGRATION=1 is set, and each model is
skipped unless it has been installed (python captain.py --install-model ...).
A real recording is needed to check separation quality; a synthetic mix of a
drum-like click track, a bass tone and a "vocal" sweep is enough to verify
that every model runs and that its stems add up to the mix.
"""

import numpy as np
import pytest
import soundfile as sf

from core import pipeline
from models import registry

pytestmark = pytest.mark.integration

SAMPLE_RATE = 44100
SECONDS = 8


@pytest.fixture(scope="module")
def mix(tmp_path_factory):
    """A short synthetic stereo mix."""
    t = np.arange(SAMPLE_RATE * SECONDS) / SAMPLE_RATE
    rng = np.random.default_rng(0)
    bass = 0.25 * np.sin(2 * np.pi * 55 * t)
    clicks = np.zeros_like(t)
    for beat in np.arange(0, SECONDS, 0.5):
        start = int(beat * SAMPLE_RATE)
        length = int(0.05 * SAMPLE_RATE)
        clicks[start:start + length] += 0.4 * rng.standard_normal(length) * np.linspace(1, 0, length)
    lead = 0.2 * np.sin(2 * np.pi * (440 + 110 * np.sin(2 * np.pi * 0.5 * t)) * t)
    mono = bass + clicks + lead
    data = np.stack([mono, 0.9 * mono], axis=1)
    path = tmp_path_factory.mktemp("mix") / "synthetic mix.wav"
    sf.write(str(path), data, SAMPLE_RATE, subtype="PCM_16")
    return path


def run(identifier, mix, tmp_path, two_stems=False):
    model = registry.create_model(identifier)
    if not model.available:
        pytest.skip(f"{identifier} is not installed")
    progress = []
    result = pipeline.separate_file(model, mix, tmp_path, two_stems=two_stems,
                                    progress=progress.append,
                                    options={"device": "auto", "demucs_shifts": 1,
                                             "demucs_overlap": 0.25, "spleeter_mwf": False})
    assert progress[-1] == 100 and progress == sorted(progress)
    assert list(result.stems) == pipeline.sort_stems(model.get_stems(two_stems))
    frames = sf.info(str(result.mix)).frames
    for stem, path in result.stems.items():
        info = sf.info(str(path))
        assert info.samplerate == SAMPLE_RATE and info.channels == 2, stem
        assert abs(info.frames - frames) <= SAMPLE_RATE // 10, f"{stem} has the wrong length"
    return result


def reconstruction_snr(result):
    """How closely the stems add up to the mix, in dB."""
    mix_data, _ = sf.read(str(result.mix), dtype="float32")
    total = np.zeros_like(mix_data)
    for path in result.stems.values():
        data, _ = sf.read(str(path), dtype="float32")
        frames = min(len(data), len(total))
        total[:frames] += data[:frames]
    error = total - mix_data
    return 10 * np.log10(np.sum(mix_data ** 2) / max(np.sum(error ** 2), 1e-12))


@pytest.mark.parametrize("identifier", [
    "demucs4:htdemucs", "demucs4:htdemucs_6s", "demucs3:hdemucs_mmi",
    "bandsplit:vocals", "bandsplit:6stems", "d3net:standard", "d3net:fast",
])
def test_model_separates_and_stems_add_up(identifier, mix, tmp_path):
    result = run(identifier, mix, tmp_path)
    assert reconstruction_snr(result) > 10, "the stems should add up to the mix"


@pytest.mark.parametrize("identifier", ["spleeter:2stems", "spleeter:4stems", "spleeter:5stems"])
def test_spleeter_separates(identifier, mix, tmp_path):
    # Spleeter only reproduces frequencies up to 11 kHz, so its stems do not add up exactly
    run(identifier, mix, tmp_path)


def test_demucs_two_stems(mix, tmp_path):
    result = run("demucs4:htdemucs", mix, tmp_path, two_stems=True)
    assert list(result.stems) == ["vocals", "no_vocals"]
    assert reconstruction_snr(result) > 10


def test_demucs_bag_of_models(mix, tmp_path):
    """htdemucs_ft runs four networks; progress must still end at 100."""
    run("demucs4:htdemucs_ft", mix, tmp_path)
