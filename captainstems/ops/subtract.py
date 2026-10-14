"""subtract: a - b, sample-exact. The clean way to get an instrumental from a vocal model."""

from __future__ import annotations

import numpy as np

from captainstems import audio
from captainstems.ops import OpResult


def run(ctx, name: str, node, plan) -> OpResult:
    a = ctx.audio(node.inputs.a)
    b = ctx.audio(node.inputs.b)
    # b is brought to a's shape; a itself is never altered
    b = audio.match_length(audio.to_channels(b, a.shape[0]), a.shape[-1])
    gain = float(node.params.gain_b)
    out = a - b if gain == 1.0 else a - gain * b
    return OpResult(stems={"out": np.ascontiguousarray(out, dtype=np.float32)})
