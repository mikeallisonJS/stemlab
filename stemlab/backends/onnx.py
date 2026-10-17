"""
ONNX backend: UVR's MDX-Net models through onnxruntime.

An MDX-Net model works on a fixed-size spectrogram and carries no config, so
its manifest supplies `onnx_params` (dim_f, dim_t, n_fft, compensate). The
audio is cut into overlapping chunks; each is transformed with an STFT, run
through the network and transformed back, as UVR does it.

Only NumPy and onnxruntime are needed, so this backend also runs on machines
without torch, including DirectML on AMD and Intel GPUs.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from stemlab import dsp
from stemlab.backends.base import Backend, BackendError, Model, ParamSpec, ProgressFn, check_cancel

HOP = 1024

# Device name -> onnxruntime execution provider
PROVIDERS = {
    "cuda": "CUDAExecutionProvider",
    "dml": "DmlExecutionProvider",
    "coreml": "CoreMLExecutionProvider",
    "cpu": "CPUExecutionProvider",
}


def _runtime():
    try:
        import onnxruntime as ort
    except ImportError:
        raise BackendError("onnxruntime is not installed. Run: stemlab bootstrap") from None
    return ort


def _preload_cuda(ort) -> None:
    """Let onnxruntime find the CUDA libraries that came with torch instead of a system install."""
    try:
        ort.preload_dlls()
    except Exception:
        try:
            import torch  # noqa: F401 - importing it loads the CUDA libraries into the process
        except ImportError:
            pass


class OnnxModel(Model):
    def __init__(self, session, device: str, stems: list[str], sample_rate: int, onnx_params: dict):
        self.session = session
        self.device = device
        self.stems = stems
        self.sample_rate = sample_rate
        self.dim_f = int(onnx_params["dim_f"])
        self.dim_t = int(onnx_params["dim_t"])
        self.n_fft = int(onnx_params["n_fft"])
        self.input_name = session.get_inputs()[0].name
        batch = session.get_inputs()[0].shape[0]
        #: Models exported with a fixed batch of 1 cannot be batched
        self.fixed_batch = batch if isinstance(batch, int) else None

    def _spectrogram(self, chunk: np.ndarray) -> np.ndarray:
        """(2, samples) -> (4, dim_f, frames): real and imaginary parts per channel."""
        planes = []
        for channel in chunk:
            spectrum = dsp.stft(channel, self.n_fft, HOP).T  # (bins, frames)
            planes += [spectrum.real, spectrum.imag]
        spec = np.stack(planes, axis=0)[:, : self.dim_f, :].astype(np.float32)
        spec[:, :3, :] = 0  # the lowest bins are never used by these models
        return spec

    def _waveform(self, spec: np.ndarray, length: int) -> np.ndarray:
        """(4, dim_f, frames) -> (2, samples)"""
        bins = self.n_fft // 2 + 1
        padded = np.zeros((4, bins, spec.shape[-1]), dtype=np.float32)
        padded[:, : self.dim_f, :] = spec
        channels = []
        for index in range(2):
            spectrum = (padded[2 * index] + 1j * padded[2 * index + 1]).T  # (frames, bins)
            channels.append(dsp.istft(spectrum, length, self.n_fft, HOP))
        return np.stack(channels, axis=0)

    def _run(self, specs: np.ndarray, denoise: bool) -> np.ndarray:
        def infer(batch: np.ndarray) -> np.ndarray:
            return self.session.run(None, {self.input_name: batch})[0]

        if denoise:
            # Averaging with the prediction for the inverted input cancels the model's own noise
            return infer(specs) * 0.5 - infer(-specs) * 0.5
        return infer(specs)

    def separate(
        self,
        audio: np.ndarray,
        sample_rate: int,
        params: dict,
        progress: ProgressFn | None = None,
        cancel: Any = None,
    ) -> dict[str, np.ndarray]:
        mix = np.ascontiguousarray(audio, dtype=np.float32)
        length = mix.shape[-1]
        overlap = float(params.get("overlap", 0.25))
        denoise = bool(params.get("denoise", False))
        batch_size = self.fixed_batch or max(1, int(params.get("batch_size", 1)))

        trim = self.n_fft // 2
        chunk_size = HOP * (self.dim_t - 1)
        gen_size = chunk_size - 2 * trim
        pad = gen_size + trim - (length % gen_size)
        mixture = np.concatenate(
            [np.zeros((2, trim), dtype=np.float32), mix, np.zeros((2, pad), dtype=np.float32)], axis=1
        )
        total = mixture.shape[-1]
        step = max(1, int((1 - overlap) * chunk_size))

        result = np.zeros((2, total), dtype=np.float32)
        divider = np.zeros(total, dtype=np.float32)
        starts = list(range(0, total, step))
        for batch_start in range(0, len(starts), batch_size):
            check_cancel(cancel)
            batch_starts = starts[batch_start : batch_start + batch_size]
            specs = []
            for start in batch_starts:
                part = mixture[:, start : start + chunk_size]
                if part.shape[-1] < chunk_size:
                    part = np.pad(part, ((0, 0), (0, chunk_size - part.shape[-1])))
                specs.append(self._spectrogram(part))
            predicted = self._run(np.stack(specs, axis=0), denoise)

            for start, spec in zip(batch_starts, predicted, strict=True):
                actual = min(chunk_size, total - start)
                wave = self._waveform(spec, chunk_size)[:, :actual]
                window = np.hanning(actual).astype(np.float32) if overlap > 0 else np.ones(actual, dtype=np.float32)
                result[:, start : start + actual] += wave * window
                divider[start : start + actual] += window
            if progress:
                progress(min(1.0, (batch_start + len(batch_starts)) / len(starts)))

        source = result / np.maximum(divider, 1e-8)
        source = source[:, trim : trim + length] * float(params.get("compensate", 1.0))
        np.nan_to_num(source, copy=False)
        if progress:
            progress(1.0)
        return {self.stems[0]: np.ascontiguousarray(source, dtype=np.float32)}

    def close(self) -> None:
        self.session = None


class OnnxBackend(Backend):
    name = "onnx"
    supported_params = {
        "device": ParamSpec("enum", "auto", "Where to run the model", choices=("auto", "cuda", "dml", "coreml", "cpu")),
        "overlap": ParamSpec("float", 0.25, "Overlap between chunks, as a fraction", minimum=0.0, maximum=0.99),
        "batch_size": ParamSpec("int", 1, "Chunks run through the model at once", minimum=1, maximum=64),
        "denoise": ParamSpec("bool", False, "Run every chunk twice with inverted phase and average (2x the time)"),
        "compensate": ParamSpec(
            "float", 1.0, "Gain applied to the output; each model's manifest carries its own", minimum=0.5, maximum=2.0
        ),
    }

    def version(self) -> dict:
        ort = _runtime()
        return {"onnxruntime": ort.__version__}

    def resolve_device(self, requested: str) -> str:
        """Pick an execution provider: the best available for `auto`, otherwise exactly what was asked for."""
        ort = _runtime()
        available = set(ort.get_available_providers())
        if requested in ("auto", None, ""):
            for name in ("cuda", "dml", "coreml"):
                if PROVIDERS[name] in available:
                    return name
            return "cpu"
        if requested == "mps":
            requested = "coreml"
        if requested not in PROVIDERS:
            raise ValueError(f"unknown device '{requested}' for the onnx backend")
        if PROVIDERS[requested] not in available:
            raise RuntimeError(
                f"device '{requested}' was requested, but this onnxruntime build only offers "
                + ", ".join(sorted(p.replace("ExecutionProvider", "") for p in available))
            )
        return requested

    def model_defaults(self, manifest) -> dict:
        compensate = (manifest.manifest.onnx_params or {}).get("compensate")
        return {"compensate": compensate} if compensate is not None else {}

    def load(self, manifest, params: dict) -> Model:
        ort = _runtime()
        info = manifest.manifest
        onnx_params = info.onnx_params or {}
        missing = [key for key in ("dim_f", "dim_t", "n_fft") if key not in onnx_params]
        if missing:
            raise BackendError(
                f"ONNX model '{info.id}' needs onnx_params {missing} in its manifest: MDX-Net models carry no config"
            )
        if len(info.stems) != 1:
            raise BackendError(f"ONNX model '{info.id}' must list exactly one stem, the one it outputs")

        device = params["device"]
        options = ort.SessionOptions()
        options.log_severity_level = 3
        if device == "dml":
            # Required by the DirectML execution provider
            options.enable_mem_pattern = False
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        if device == "cuda":
            _preload_cuda(ort)
        providers = [PROVIDERS[device]] + (["CPUExecutionProvider"] if device != "cpu" else [])
        try:
            session = ort.InferenceSession(str(manifest.weight_paths[0]), sess_options=options, providers=providers)
        except Exception as e:
            raise BackendError(f"Could not load ONNX model '{info.id}': {e}") from None
        if device != "cpu" and session.get_providers()[0] != PROVIDERS[device]:
            raise BackendError(
                f"onnxruntime could not start its {device} provider for '{info.id}' and would silently run on the "
                "CPU. Check the GPU libraries with `stemlab doctor`, or set device: cpu."
            )

        shape = session.get_inputs()[0].shape
        expected = [4, int(onnx_params["dim_f"]), int(onnx_params["dim_t"])]
        if list(shape[1:]) != expected:
            raise BackendError(
                f"ONNX model '{info.id}' expects input {shape[1:]}, but its manifest describes {expected}"
            )
        return OnnxModel(session, device, list(info.stems), info.sample_rate, onnx_params)


def create() -> Backend:
    return OnnxBackend()
