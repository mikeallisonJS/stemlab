"""Shared fixtures. Tests never touch the real ~/.captainstems unless they ask for models."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

FIXTURES = Path(__file__).parent / "fixtures"

# Model tests reuse the real registry so weights are downloaded once; everything
# else runs against a throwaway home.
REAL_HOME = os.environ.get("CAPTAINSTEMS_HOME") or str(Path.home() / ".captainstems")
os.environ["CAPTAINSTEMS_HOME"] = tempfile.mkdtemp(prefix="captainstems_test_home_")


@pytest.fixture
def clip() -> Path:
    """The 5 second synthetic stereo clip."""
    return FIXTURES / "clip-5s.flac"


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """A fresh, empty CaptainStems home for one test."""
    monkeypatch.setenv("CAPTAINSTEMS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def real_home(monkeypatch) -> Path:
    """The user's real home, for tests that need downloaded model weights."""
    monkeypatch.setenv("CAPTAINSTEMS_HOME", REAL_HOME)
    return Path(REAL_HOME)


def write_tone(path, seconds=1.0, sample_rate=44100, channels=2, frequency=440.0, amplitude=0.5,
               subtype="PCM_16") -> Path:
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    tone = amplitude * np.sin(2 * np.pi * frequency * t)
    data = np.stack([tone] * channels, axis=1)
    sf.write(str(path), data, sample_rate, subtype=subtype)
    return Path(path)


@pytest.fixture
def tone(tmp_path) -> Path:
    return write_tone(tmp_path / "tone.wav")
