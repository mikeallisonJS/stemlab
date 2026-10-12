"""
Native Demucs backend: loads `.th` bags from the registry and runs them with
`demucs.apply.apply_model`.

A Demucs manifest names the bag's yaml as `config` and its `.th` files as
`weights`; both live in the model's folder, which is used as a local repo.
"""

from __future__ import annotations

import random
from typing import Any

import numpy as np

from captainstems.backends.base import (
    COMMON_PARAMS,
    Backend,
    BackendError,
    Model,
    ParamSpec,
    ProgressFn,
    check_cancel,
)


class DemucsModel(Model):
    def __init__(self, model, device: str, stems: list[str], sample_rate: int):
        self.model = model
        self.device = device
        self.stems = stems
        self.sample_rate = sample_rate

    def separate(
        self, audio: np.ndarray, sample_rate: int, params: dict, progress: ProgressFn | None = None, cancel: Any = None
    ) -> dict[str, np.ndarray]:
        import torch
        from demucs.apply import apply_model

        mix = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32))
        # The reference implementation always normalizes by the mono mix
        reference = mix.mean(0)
        mean, std = reference.mean(), reference.std()
        std = std if float(std) > 1e-8 else torch.tensor(1.0)
        mix = (mix - mean) / std

        shifts = int(params.get("shifts", 1))
        length = mix.shape[-1]
        segment = params.get("segment")
        segment_seconds = float(segment or getattr(self.model, "segment", None) or 7.8)
        segment_length = segment_seconds * self.sample_rate

        def on_segment(info: dict) -> None:
            check_cancel(cancel)
            if progress is None or info.get("state") != "end":
                return
            models = max(1, int(info.get("models", 1)))
            passes = models * max(1, shifts)
            done = int(info.get("model_idx_in_bag", 0)) * max(1, shifts) + int(info.get("shift_idx", 0))
            # segment_offset is where the segment that just finished started
            within = min(1.0, (float(info.get("segment_offset", 0)) + segment_length) / max(1, length))
            progress(min(1.0, (done + within) / passes))

        # Demucs draws its time shifts from Python's global random generator.
        # Seeding it makes a run repeatable from the parameters in run.json.
        random_state = random.getstate()
        random.seed(int(params.get("seed", 0)))
        try:
            with torch.no_grad():
                out = apply_model(
                    self.model,
                    mix[None],
                    shifts=shifts,
                    split=bool(params.get("split", True)),
                    overlap=float(params.get("overlap", 0.25)),
                    segment=float(segment) if segment else None,
                    device=self.device,
                    progress=False,
                    callback=on_segment,
                    callback_arg={},
                )[0]
        finally:
            random.setstate(random_state)
        check_cancel(cancel)
        out = out * std + mean
        result = out.cpu().numpy().astype(np.float32)
        if progress:
            progress(1.0)
        return {stem: result[index] for index, stem in enumerate(self.stems)}

    def close(self) -> None:
        import torch

        self.model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


class DemucsBackend(Backend):
    name = "demucs"
    supported_params = {
        "device": COMMON_PARAMS["device"],
        "shifts": ParamSpec(
            "int", 1, "Random time shifts averaged together; each one is a full extra pass", minimum=0, maximum=20
        ),
        "overlap": ParamSpec("float", 0.25, "Overlap between segments, as a fraction", minimum=0.0, maximum=0.95),
        "segment": ParamSpec(
            "float", 0.0, "Segment length in seconds; 0 uses the model's own", minimum=0.0, maximum=600.0
        ),
        "split": ParamSpec("bool", True, "Process in segments; turning it off needs far more memory"),
        "seed": ParamSpec(
            "int", 0, "Seed for the random time shifts, so a run can be repeated exactly", minimum=0, maximum=2**31 - 1
        ),
    }

    def version(self) -> dict:
        import demucs
        import torch

        return {"demucs": demucs.__version__, "torch": torch.__version__}

    def load(self, manifest, params: dict) -> Model:
        from demucs.pretrained import get_model

        registered = manifest
        info = registered.manifest
        if not info.config:
            raise BackendError(f"Demucs model '{info.id}' needs `config` set to its bag .yaml file")
        name = info.config.rsplit(".", 1)[0]
        try:
            model = get_model(name=name, repo=registered.folder)
        except BaseException as e:  # demucs reports loading problems with SystemExit
            raise BackendError(f"Could not load Demucs model '{info.id}': {e}") from None
        model.eval()
        sources = list(model.sources)
        if sources != list(info.stems):
            raise BackendError(f"Demucs model '{info.id}' produces {sources}, but its manifest lists {info.stems}")
        return DemucsModel(model, params["device"], sources, int(model.samplerate))


def create() -> Backend:
    return DemucsBackend()
