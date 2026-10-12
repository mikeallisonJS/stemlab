"""postprocess: run a single-purpose model (dereverb, denoise, de-echo) on one stem."""

from __future__ import annotations

from captainstems.ops import OpResult
from captainstems.ops.separate import separate_audio


def run(ctx, name: str, node, plan) -> OpResult:
    stems, info = separate_audio(ctx, name, plan, ctx.audio(node.inputs.audio))
    info["kept"] = plan.keep
    return OpResult(stems={"out": stems[plan.keep]}, info=info)
