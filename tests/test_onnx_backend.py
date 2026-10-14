import threading

import numpy as np
import pytest

from captainstems.backends import onnx as onnx_backend
from captainstems.backends.base import Cancelled
from captainstems.backends.onnx import OnnxBackend, OnnxModel


class Input:
    def __init__(self, shape):
        self.name = "input"
        self.shape = shape


class IdentitySession:
    """Stands in for onnxruntime: a network that returns its input unchanged."""

    def __init__(self, shape=("batch_size", 4, 1025, 32), gain=1.0):
        self.shape = list(shape)
        self.gain = gain
        self.batches = []

    def get_inputs(self):
        return [Input(self.shape)]

    def run(self, _outputs, feed):
        batch = feed["input"]
        self.batches.append(batch.shape)
        return [batch * self.gain]


PARAMS = {"dim_f": 1025, "dim_t": 32, "n_fft": 2048}


def close(out, expected, atol=2e-3):
    """
    Compare away from the first and last samples: MDX-Net models never see the
    three lowest frequency bins, which shows as a small error where the track
    starts and stops abruptly.
    """
    middle = slice(4096, -4096)
    return np.allclose(out[:, middle], expected[:, middle], atol=atol) and np.allclose(out, expected, atol=0.05)


def tone(seconds=2.0, frequency=440.0):
    t = np.arange(int(44100 * seconds)) / 44100
    wave = (0.5 * np.sin(2 * np.pi * frequency * t)).astype(np.float32)
    return np.stack([wave, 0.5 * wave])


def test_chunking_and_stft_reconstruct_the_signal():
    """With an identity network the whole pipeline must hand back its input."""
    session = IdentitySession()
    model = OnnxModel(session, "cpu", ["vocals"], 44100, PARAMS)
    audio = tone()
    progress = []
    result = model.separate(audio, 44100, {"overlap": 0.25, "batch_size": 4}, progress=progress.append)

    assert list(result) == ["vocals"]
    out = result["vocals"]
    assert out.shape == audio.shape and out.dtype == np.float32
    assert close(out, audio)
    assert progress == sorted(progress) and progress[-1] == 1.0
    assert all(shape[1:] == (4, 1025, 32) for shape in session.batches)
    assert max(shape[0] for shape in session.batches) == 4


@pytest.mark.parametrize("overlap", [0.0, 0.5, 0.9])
def test_every_overlap_covers_the_whole_track(overlap):
    model = OnnxModel(IdentitySession(), "cpu", ["vocals"], 44100, PARAMS)
    audio = tone(seconds=1.3)
    out = model.separate(audio, 44100, {"overlap": overlap})["vocals"]
    assert out.shape == audio.shape
    # Without overlap the chunk borders are not cross-faded, so be lenient there
    assert close(out, audio, atol=0.05 if overlap == 0 else 2e-3)


def test_compensate_and_denoise():
    audio = tone()
    plain = OnnxModel(IdentitySession(), "cpu", ["vocals"], 44100, PARAMS)
    boosted = plain.separate(audio, 44100, {"compensate": 1.25})["vocals"]
    assert close(boosted, audio * 1.25, atol=3e-3)

    session = IdentitySession()
    denoised = OnnxModel(session, "cpu", ["vocals"], 44100, PARAMS).separate(audio, 44100, {"denoise": True})
    assert close(denoised["vocals"], audio)
    assert len(session.batches) % 2 == 0, "denoise runs every batch twice"


def test_models_with_a_fixed_batch_are_run_one_chunk_at_a_time():
    session = IdentitySession(shape=(1, 4, 1025, 32))
    model = OnnxModel(session, "cpu", ["vocals"], 44100, PARAMS)
    model.separate(tone(), 44100, {"batch_size": 8})
    assert {shape[0] for shape in session.batches} == {1}


def test_frequencies_above_dim_f_are_dropped():
    """A model with fewer bins than the STFT only ever sees and returns the lower band."""
    params = {"dim_f": 256, "dim_t": 32, "n_fft": 2048}
    session = IdentitySession(shape=("batch_size", 4, 256, 32))
    model = OnnxModel(session, "cpu", ["vocals"], 44100, params)
    low = model.separate(tone(frequency=440.0), 44100, {})["vocals"]
    high = model.separate(tone(frequency=12000.0), 44100, {})["vocals"]
    assert np.sqrt(np.mean(low**2)) > 0.2
    assert np.sqrt(np.mean(high**2)) < 0.01


def test_cancel_stops_between_batches():
    cancel = threading.Event()
    session = IdentitySession()
    original = session.run

    def run_then_cancel(outputs, feed):
        cancel.set()
        return original(outputs, feed)

    session.run = run_then_cancel
    with pytest.raises(Cancelled):
        OnnxModel(session, "cpu", ["vocals"], 44100, PARAMS).separate(tone(), 44100, {}, cancel=cancel)
    assert len(session.batches) == 1


def test_device_resolution_uses_the_available_providers(monkeypatch):
    class Runtime:
        providers = ["CPUExecutionProvider"]

        @classmethod
        def get_available_providers(cls):
            return cls.providers

    monkeypatch.setattr(onnx_backend, "_runtime", lambda: Runtime)
    backend = OnnxBackend()
    assert backend.resolve_device("auto") == "cpu"
    with pytest.raises(RuntimeError, match="only offers CPU"):
        backend.resolve_device("cuda")

    Runtime.providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
    assert backend.resolve_device("auto") == "dml"
    Runtime.providers = ["CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"]
    assert backend.resolve_device("auto") == "cuda"
    assert backend.resolve_device("cpu") == "cpu"
    Runtime.providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    assert backend.resolve_device("mps") == "coreml"
    with pytest.raises(ValueError):
        backend.resolve_device("vulkan")


def test_manifest_compensate_becomes_the_default(home):
    from captainstems.registry import Manifest, Model

    manifest = Manifest(
        id="mdx", backend="onnx", weights="model.onnx", stems=["vocals"], onnx_params={**PARAMS, "compensate": 1.009}
    )
    assert OnnxBackend().model_defaults(Model(home, manifest)) == {"compensate": 1.009}
    bare = Manifest(id="mdx", backend="onnx", weights="model.onnx", stems=["vocals"])
    assert OnnxBackend().model_defaults(Model(home, bare)) == {}
