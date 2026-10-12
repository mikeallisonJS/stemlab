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


def write_tone(
    path, seconds=1.0, sample_rate=44100, channels=2, frequency=440.0, amplitude=0.5, subtype="PCM_16"
) -> Path:
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    tone = amplitude * np.sin(2 * np.pi * frequency * t)
    data = np.stack([tone] * channels, axis=1)
    sf.write(str(path), data, sample_rate, subtype=subtype)
    return Path(path)


@pytest.fixture
def tone(tmp_path) -> Path:
    return write_tone(tmp_path / "tone.wav")


class FakeModel:
    """Splits its input into fixed shares, so the stems add up to the mix exactly."""

    SHARES = {"vocals": 0.5, "other": 0.5, "drums": 0.25, "bass": 0.25, "dry": 1.0}

    def __init__(self, backend, manifest, params):
        self.backend = backend
        self.stems = list(manifest.manifest.stems)
        self.sample_rate = manifest.manifest.sample_rate
        self.adjustments = list(backend.adjustments)
        self.closed = False

    def separate(self, audio, sample_rate, params, progress=None, cancel=None):
        from captainstems.backends.base import check_cancel

        self.backend.calls.append({"params": dict(params), "shape": audio.shape, "sample_rate": sample_rate})
        result = {}
        for index, stem in enumerate(self.stems):
            check_cancel(cancel)
            if self.backend.cancel_after is not None and index >= self.backend.cancel_after:
                self.backend.cancel_flag.set()
            if self.backend.fail:
                raise RuntimeError("the fake model failed")
            share = self.SHARES.get(stem, 1.0 / len(self.stems))
            result[stem] = (audio * share).astype(np.float32)
            if progress:
                progress((index + 1) / len(self.stems))
        return result

    def close(self):
        self.closed = True


class FakeBackend:
    """Stands in for a real backend: no torch, no weights."""

    name = "msst"

    def __init__(self):
        from captainstems.backends.base import COMMON_PARAMS, ParamSpec

        self.supported_params = {
            **COMMON_PARAMS,
            "chunk_size": ParamSpec("int", 352800, "chunk", minimum=44100, maximum=2646000),
            "overlap": ParamSpec("int", 2, "overlap", minimum=1, maximum=32),
            "batch_size": ParamSpec("int", 1, "batch", minimum=1, maximum=64),
            "shifts": ParamSpec("int", 1, "shifts", minimum=1, maximum=16),
        }
        self.calls = []
        self.loads = []
        self.adjustments = []
        self.fail = False
        self.cancel_after = None
        self.cancel_flag = None
        self.config_defaults = {}

    def version(self):
        return {"fake": "1.0"}

    def device_defaults(self, device, vram_mb):
        return {"overlap": 3, "batch_size": 2}

    def model_defaults(self, manifest):
        return dict(self.config_defaults)

    def load(self, manifest, params):
        self.loads.append(manifest.id)
        return FakeModel(self, manifest, params)

    def available(self):
        return None


@pytest.fixture
def fake_backend(monkeypatch):
    """Replace every backend with a fake that needs neither torch nor weights."""
    from captainstems.backends import base, device

    backend = FakeBackend()
    monkeypatch.setattr(base, "_instances", {name: backend for name in base.BACKENDS})
    # Behave like a machine without a GPU, whatever the tests run on
    monkeypatch.setattr(
        device, "torch_state", lambda: {"version": None, "cuda": False, "mps": False, "device_name": None}
    )
    monkeypatch.setattr(device, "vram_mb", lambda: None)
    return backend


def add_fake_model(registry, model_id, stems, sample_rate=44100, defaults=None, backend="msst"):
    """Register a model whose weights are a small dummy file."""
    from captainstems.registry import Manifest

    folder = registry.root / model_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "config.yaml").write_text("inference: {}\n", encoding="utf-8")
    (folder / "model.ckpt").write_bytes(f"weights of {model_id}".encode())
    manifest = Manifest(
        id=model_id,
        backend=backend,
        arch="fake",
        config="config.yaml",
        weights="model.ckpt",
        stems=stems,
        sample_rate=sample_rate,
        defaults=defaults or {},
    )
    return registry.add(manifest)


@pytest.fixture
def registry(home, fake_backend):
    """A registry in a fresh home with a few fake models installed."""
    from captainstems.registry import Registry

    registry = Registry()
    add_fake_model(registry, "vocal-model", ["vocals"])
    add_fake_model(registry, "two-stem", ["vocals", "other"])
    add_fake_model(registry, "four-stem", ["vocals", "drums", "bass", "other"])
    add_fake_model(registry, "dereverb", ["dry"])
    return registry
