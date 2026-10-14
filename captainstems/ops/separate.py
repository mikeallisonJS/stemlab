"""separate: run one model on one input and emit its stems."""

from __future__ import annotations

import numpy as np

from captainstems import audio
from captainstems.ops import OpResult


def separate_audio(ctx, name: str, plan, source: np.ndarray) -> tuple[dict[str, np.ndarray], dict]:
    """
    Run the node's model on `source` (at the run's sample rate) and return
    every stem the model produces, converted back to that sample rate and
    to exactly the length of the input.
    """
    model = ctx.model(plan)
    length = source.shape[-1]
    model_input = audio.to_channels(source, 2)
    if model.sample_rate != ctx.sample_rate:
        model_input = audio.resample(model_input, ctx.sample_rate, model.sample_rate)

    stems = model.separate(model_input, model.sample_rate, plan.params, progress=ctx.progress(name), cancel=ctx.cancel)

    result = {}
    for stem, data in stems.items():
        if model.sample_rate != ctx.sample_rate:
            data = audio.resample(data, model.sample_rate, ctx.sample_rate)
        result[stem] = np.ascontiguousarray(audio.match_length(data, length), dtype=np.float32)

    info = {}
    adjustments = list(getattr(model, "adjustments", []) or [])
    if adjustments:
        info["adjustments"] = adjustments
        for message in adjustments:
            ctx.warn(name, message)
    return result, info


def run(ctx, name: str, node, plan) -> OpResult:
    stems, info = separate_audio(ctx, name, plan, ctx.audio(node.inputs.audio))
    # Every stem is kept (and cached), so changing `targets` later costs nothing
    return OpResult(stems=stems, info=info)
