"""Shared fixtures for the CaptainStems test suite."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Must be set before Qt is loaded
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from ui.qt_env import quiet_multimedia_logging
quiet_multimedia_logging()

# Only the integration tests use the real application data (installed models)
RUN_INTEGRATION = os.environ.get("CAPTAINSTEMS_INTEGRATION") == "1"
if not RUN_INTEGRATION:
    os.environ["CAPTAINSTEMS_HOME"] = tempfile.mkdtemp(prefix="captainstems_test_home_")

import numpy as np
import pytest
import soundfile as sf


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: runs real models (set CAPTAINSTEMS_INTEGRATION=1 to enable)")


def pytest_collection_modifyitems(config, items):
    skip_integration = pytest.mark.skip(reason="set CAPTAINSTEMS_INTEGRATION=1 to run real models")
    skip_unit = pytest.mark.skip(reason="unit tests are skipped while CAPTAINSTEMS_INTEGRATION=1")
    for item in items:
        if "integration" in item.keywords:
            if not RUN_INTEGRATION:
                item.add_marker(skip_integration)
        elif RUN_INTEGRATION:
            # Unit tests must never touch the real application data
            item.add_marker(skip_unit)


def pytest_sessionfinish(session, exitstatus):
    if not RUN_INTEGRATION:
        shutil.rmtree(os.environ["CAPTAINSTEMS_HOME"], ignore_errors=True)


def write_tone(path, seconds=2.0, sample_rate=44100, channels=2, subtype="PCM_16", frequency=440.0):
    """Write a sine tone to an audio file."""
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    tone = 0.5 * np.sin(2 * np.pi * frequency * t)
    data = np.stack([tone] * channels, axis=1) if channels > 1 else tone
    sf.write(str(path), data, sample_rate, subtype=subtype)
    return Path(path)


@pytest.fixture
def tone_wav(tmp_path):
    """A 2 second stereo 44.1 kHz 16-bit WAV file."""
    return write_tone(tmp_path / "tone.wav")


@pytest.fixture
def settings(tmp_path):
    """Application settings stored in a temporary file."""
    from PyQt6.QtCore import QSettings
    from core.settings import Settings
    return Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))


@pytest.fixture
def fake_model_class():
    """
    A model that "separates" by copying its input into each stem, without
    needing an installed backend.
    """
    from core.process import ProcessCancelled
    from models.base_model import BaseModel, ModelError

    class FakeModel(BaseModel):
        BACKEND = "fake"
        AVAILABLE_MODELS = {"basic": "Copies the input", "broken": "Always fails"}
        SEPARATION_MODES = {"basic": ["vocals", "drums"], "broken": ["vocals"]}

        def __init__(self, model_name="basic"):
            super().__init__(model_name)
            self.name = f"Fake ({model_name})"
            self.available = True
            self.calls = []

        @property
        def supports_two_stems(self):
            return True

        def get_stems(self, two_stems=False):
            return ["vocals", "no_vocals"] if two_stems else super().get_stems()

        def _install(self, log, cancel_event):
            pass

        def _separate(self, input_wav, raw_dir, two_stems, progress, status, cancel_event, options):
            self.calls.append({"two_stems": two_stems, "options": dict(options)})
            if self.model_name == "broken":
                raise ModelError("the fake model is broken")
            status("Separating stems...")
            stems = {}
            names = self.get_stems(two_stems)
            for index, stem in enumerate(names):
                if cancel_event is not None and cancel_event.is_set():
                    raise ProcessCancelled()
                stems[stem] = raw_dir / f"{stem}.wav"
                shutil.copy2(input_wav, stems[stem])
                progress(100 * (index + 1) / len(names))
            return stems

    return FakeModel
