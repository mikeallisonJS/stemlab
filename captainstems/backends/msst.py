"""
MSST backend: any model ZFTurbo's Music-Source-Separation-Training can build
from a config YAML and a checkpoint (bs_roformer, mel_band_roformer, mdx23c,
scnet, bandit, htdemucs and more).

The upstream repository is a pinned submodule at third_party/msst and is not
modified. Its model constructors are called directly; the chunked overlap-add
loop below follows upstream's `demix` so that progress, cancellation and
out-of-memory recovery work per chunk. Keeping all of that in this one file
means an upstream change breaks one place.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import numpy as np

from captainstems import paths
from captainstems.backends.base import (
    COMMON_PARAMS,
    Backend,
    BackendError,
    Model,
    ParamSpec,
    ProgressFn,
    check_cancel,
)

# Smallest values the out-of-memory fallback will go down to
MIN_BATCH_SIZE = 1
MIN_CHUNK_SIZE = 44100


def _import_upstream():
    """Make the submodule importable. Its packages are named `models` and `utils`."""
    if not (paths.MSST_DIR / "utils" / "settings.py").is_file():
        raise BackendError("The MSST submodule is missing. Run: git submodule update --init third_party/msst")
    root = str(paths.MSST_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from utils.model_utils import _getWindowingArray, prefer_target_instrument
        from utils.settings import get_model_from_config
    except ImportError as e:
        raise BackendError(f"MSST's dependencies are not installed ({e}). Run: captainstems bootstrap") from None
    return get_model_from_config, prefer_target_instrument, _getWindowingArray


def _state_dict(checkpoint: Any) -> dict:
    """Checkpoints wrap their weights under different keys depending on who trained them."""
    for key in ("state", "state_dict", "model_state_dict"):
        if isinstance(checkpoint, dict) and key in checkpoint and isinstance(checkpoint[key], dict):
            checkpoint = checkpoint[key]
    return checkpoint


class MsstModel(Model):
    def __init__(self, model, config, arch: str, device: str, stems: list[str], sample_rate: int, windowing):
        self.model = model
        self.config = config
        self.arch = arch
        self.device = device
        self.stems = stems
        self.sample_rate = sample_rate
        self._windowing = windowing
        #: What the out-of-memory fallback changed during the last run
        self.adjustments: list[str] = []

    # Parameters ----------------------------------------------------------------

    @property
    def demucs_mode(self) -> bool:
        return self.arch == "htdemucs"

    # Inference -----------------------------------------------------------------

    def _demix(
        self, mix, chunk_size: int, overlap: int, batch_size: int, use_fp16: bool, on_chunk, cancel
    ) -> np.ndarray:
        """
        Overlap-add inference over the whole track.

        Args:
            mix: torch tensor of shape (channels, samples) on the CPU

        Returns:
            Array of shape (stems, channels, samples)
        """
        import torch
        from torch import nn

        device = torch.device(self.device)
        step = max(1, chunk_size // max(1, overlap))
        generic = not self.demucs_mode
        length = mix.shape[-1]

        border = 0
        if generic:
            fade_size = chunk_size // 10
            border = chunk_size - step
            if border == 0:
                # overlap 1: chunks only touch, so fading their edges would mute the seams
                fade_size = 0
                windowing = torch.ones(chunk_size)
            else:
                windowing = self._windowing(chunk_size, fade_size)
            # Reflect padding keeps the first and last seconds out of the fades
            if length > 2 * border and border > 0:
                mix = nn.functional.pad(mix, (border, border), mode="reflect")
            else:
                border = 0

        total = mix.shape[-1]
        result = torch.zeros((len(self.stems),) + tuple(mix.shape), dtype=torch.float32)
        counter = torch.zeros(total, dtype=torch.float32)
        autocast_device = "cuda" if device.type == "cuda" else "cpu"

        position = 0
        batch, locations = [], []
        with torch.inference_mode():
            while position < total:
                check_cancel(cancel)
                part = mix[:, position : position + chunk_size]
                chunk_length = part.shape[-1]
                pad_mode = "reflect" if generic and chunk_length > chunk_size // 2 else "constant"
                part = nn.functional.pad(part, (0, chunk_size - chunk_length), mode=pad_mode, value=0)
                batch.append(part)
                locations.append((position, chunk_length))
                position += step

                if len(batch) >= batch_size or position >= total:
                    arr = torch.stack(batch, dim=0).to(device)
                    with torch.autocast(
                        device_type=autocast_device, dtype=torch.float16, enabled=use_fp16 and device.type == "cuda"
                    ):
                        out = self.model(arr)
                    out = out.to("cpu", torch.float32)
                    if out.dim() == 3:
                        # Single-target models return (batch, channels, samples)
                        out = out.unsqueeze(1)

                    if generic:
                        window = windowing.clone()
                        if fade_size and position - step == 0:
                            window[:fade_size] = 1  # first chunk: no fade in
                        elif fade_size and position >= total:
                            window[-fade_size:] = 1  # last chunk: no fade out
                    for index, (start, seg_length) in enumerate(locations):
                        if generic:
                            result[..., start : start + seg_length] += (
                                out[index, ..., :seg_length] * window[:seg_length]
                            )
                            counter[start : start + seg_length] += window[:seg_length]
                        else:
                            result[..., start : start + seg_length] += out[index, ..., :seg_length]
                            counter[start : start + seg_length] += 1.0
                    batch.clear()
                    locations.clear()
                    del arr, out
                    on_chunk(min(1.0, position / total))

        estimated = result / counter.clamp_min(1e-8)
        if border:
            estimated = estimated[..., border:-border]
        estimated = estimated.numpy()
        np.nan_to_num(estimated, copy=False, nan=0.0)
        return estimated

    def _demix_with_fallback(self, mix, settings: dict, on_chunk, cancel) -> np.ndarray:
        """Run `_demix`, shrinking the batch and then the chunk when the GPU runs out of memory."""
        import torch

        while True:
            try:
                return self._demix(
                    mix,
                    settings["chunk_size"],
                    settings["overlap"],
                    settings["batch_size"],
                    settings["fp16"],
                    on_chunk,
                    cancel,
                )
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                if settings["batch_size"] > MIN_BATCH_SIZE:
                    settings["batch_size"] = max(MIN_BATCH_SIZE, settings["batch_size"] // 2)
                    change = f"batch_size lowered to {settings['batch_size']}"
                elif settings["chunk_size"] // 2 >= MIN_CHUNK_SIZE and not self.demucs_mode:
                    settings["chunk_size"] //= 2
                    change = f"chunk_size lowered to {settings['chunk_size']}"
                else:
                    raise BackendError(
                        "The GPU ran out of memory even with batch_size 1 and the smallest chunk. "
                        "Use device: cpu or a smaller model."
                    ) from None
                self.adjustments.append(f"GPU out of memory: {change}")

    def separate(
        self, audio: np.ndarray, sample_rate: int, params: dict, progress: ProgressFn | None = None, cancel: Any = None
    ) -> dict[str, np.ndarray]:
        import torch

        self.adjustments = []
        mix = np.ascontiguousarray(audio, dtype=np.float32)

        mean = std = None
        if params.get("normalize"):
            mono = mix.mean(0)
            mean, std = float(mono.mean()), float(mono.std())
            if std > 1e-8:
                mix = (mix - mean) / std
            else:
                mean = std = None

        settings = {
            "chunk_size": int(params["chunk_size"]),
            "overlap": int(params.get("overlap", 2)),
            "batch_size": int(params.get("batch_size", 1)),
            "fp16": params.get("dtype") == "fp16",
        }
        shifts = max(1, int(params.get("shifts", 1)))
        tta = bool(params.get("tta", False))

        # Every pass is one full run over the track; progress is spread across them
        passes: list[tuple[str, int]] = [("plain", shift) for shift in range(shifts)]
        if tta:
            passes += [("swap", shift) for shift in range(shifts)] + [("invert", shift) for shift in range(shifts)]

        total = np.zeros((len(self.stems),) + mix.shape, dtype=np.float32)
        length = mix.shape[-1]
        for index, (kind, shift_index) in enumerate(passes):
            shift = (length // shifts) * shift_index
            variant = mix
            if kind == "swap":
                variant = variant[::-1]
            elif kind == "invert":
                variant = -variant
            if shift:
                variant = np.concatenate((variant[:, -shift:], variant[:, :-shift]), axis=-1)

            def on_chunk(fraction: float, index=index) -> None:
                if progress:
                    progress((index + fraction) / len(passes))

            estimate = self._demix_with_fallback(
                torch.from_numpy(np.ascontiguousarray(variant)), settings, on_chunk, cancel
            )
            if shift:
                estimate = np.concatenate((estimate[..., shift:], estimate[..., :shift]), axis=-1)
            if kind == "swap":
                estimate = estimate[:, ::-1]
            elif kind == "invert":
                estimate = -estimate
            total += estimate

        total /= len(passes)
        if mean is not None:
            total = total * std + mean
        if progress:
            progress(1.0)
        return {stem: np.ascontiguousarray(total[index]) for index, stem in enumerate(self.stems)}

    def close(self) -> None:
        import torch

        self.model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


class MsstBackend(Backend):
    name = "msst"
    supported_params = {
        **COMMON_PARAMS,
        "chunk_size": ParamSpec(
            "int",
            352800,
            "Samples per chunk; the model's config sets the default",
            minimum=MIN_CHUNK_SIZE,
            maximum=44100 * 60,
        ),
        "overlap": ParamSpec(
            "int", 2, "How many chunks overlap at any point; more is slower and smoother", minimum=1, maximum=32
        ),
        "batch_size": ParamSpec(
            "int", 1, "Chunks run through the model at once; limited by VRAM", minimum=1, maximum=64
        ),
        "shifts": ParamSpec(
            "int", 1, "Passes over the track at different time offsets, averaged", minimum=1, maximum=16
        ),
        "tta": ParamSpec("bool", False, "Also run with swapped channels and inverted polarity (3x the time)"),
    }

    def version(self) -> dict:
        import torch

        _import_upstream()
        commit = "unknown"
        stamp = paths.MSST_DIR / "COMMIT"
        if stamp.is_file():
            # The packaged app ships MSST without its .git; the build writes the commit here
            return {"msst": stamp.read_text(encoding="utf-8").strip() or commit, "torch": torch.__version__}
        try:
            commit = (
                subprocess.run(
                    ["git", "-C", str(paths.MSST_DIR), "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                ).stdout.strip()
                or commit
            )
        except (OSError, subprocess.SubprocessError):
            pass
        return {"msst": commit, "torch": torch.__version__}

    def device_defaults(self, device: str, vram_mb: int | None) -> dict:
        from captainstems.backends.device import device_defaults

        defaults = device_defaults(device, vram_mb)
        return {key: defaults[key] for key in ("chunk_size", "overlap", "batch_size")}

    def model_defaults(self, manifest) -> dict:
        """
        The chunk size comes from the model's config: it is tied to how the
        model was trained. Overlap and batch size are left to the device
        defaults, which know how much memory there is.
        """
        import yaml

        info = manifest.manifest
        try:
            with open(manifest.config_path, encoding="utf-8") as f:
                config = yaml.load(f, Loader=yaml.FullLoader) or {}
        except Exception as e:
            raise BackendError(f"Cannot read the config of '{info.id}': {e}") from None
        inference = config.get("inference") or {}
        training = config.get("training") or {}
        audio_section = config.get("audio") or {}
        defaults = {}
        if info.arch == "htdemucs" and "segment" in training and "samplerate" in training:
            defaults["chunk_size"] = int(training["samplerate"] * training["segment"])
        elif "chunk_size" in inference:
            defaults["chunk_size"] = int(inference["chunk_size"])
        elif "chunk_size" in audio_section:
            defaults["chunk_size"] = int(audio_section["chunk_size"])
        if isinstance(inference.get("normalize"), bool):
            defaults["normalize"] = inference["normalize"]
        return defaults

    def load(self, manifest, params: dict) -> Model:
        import torch

        get_model_from_config, prefer_target_instrument, windowing = _import_upstream()
        info = manifest.manifest
        if not info.config or not info.arch:
            raise BackendError(f"MSST model '{info.id}' needs both `arch` and `config` in its manifest")

        try:
            model, config = get_model_from_config(info.arch, str(manifest.config_path))
        except ImportError as e:
            # A few architectures need libraries the bootstrap leaves out
            raise BackendError(
                f"The '{info.arch}' architecture of '{info.id}' needs an extra Python package ({e}). "
                f"Install it into this environment with: uv pip install {e.name or '<package>'}"
            ) from None
        except Exception as e:
            raise BackendError(f"Could not build MSST model '{info.id}' ({info.arch}): {e}") from e
        arch = config.training.get("model_type", info.arch) if "training" in config else info.arch

        weights = manifest.weight_paths[0]
        try:
            checkpoint = torch.load(str(weights), map_location="cpu", weights_only=True)
        except Exception as e:
            if not info.unsafe_pickle:
                raise BackendError(
                    f"The checkpoint of '{info.id}' cannot be loaded safely ({type(e).__name__}). "
                    'If you trust its source, set "unsafe_pickle": true in its manifest.'
                ) from None
            checkpoint = torch.load(str(weights), map_location="cpu", weights_only=False)
        try:
            model.load_state_dict(_state_dict(checkpoint))
        except Exception as e:
            raise BackendError(
                f"The checkpoint of '{info.id}' does not fit its config ({info.config}): {str(e)[:400]}"
            ) from None
        model.eval().to(params["device"])

        stems = list(prefer_target_instrument(config))
        if stems != list(info.stems):
            raise BackendError(f"MSST model '{info.id}' produces {stems}, but its manifest lists {info.stems}")
        sample_rate = (
            int(getattr(config.audio, "sample_rate", info.sample_rate))
            if "audio" in config
            else int(config.training.samplerate)
        )
        return MsstModel(model, config, arch, params["device"], stems, sample_rate, windowing)


def create() -> Backend:
    return MsstBackend()
