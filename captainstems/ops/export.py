"""export: write stems to files."""

from __future__ import annotations

import re

from captainstems import audio
from captainstems.ops import OpResult
from captainstems.recipe import export_labels

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str) -> str:
    """A file name valid on every platform."""
    cleaned = _UNSAFE.sub("_", name).strip().rstrip(". ")
    return cleaned or "stem"


def run(ctx, name: str, node, plan) -> OpResult:
    params = node.params
    target_rate = params.sample_rate or ctx.sample_rate
    written = []
    labels = export_labels(node)
    for index, (label, reference) in enumerate(labels.items()):
        ctx.check_cancel()
        data = ctx.audio(reference)
        if target_rate != ctx.sample_rate:
            data = audio.resample(data, ctx.sample_rate, target_rate)
        file_name = safe_name(params.naming.format(track=ctx.track, stem=label, node=name, recipe=ctx.recipe.name))
        # Files go to a staging folder and only move into place when the whole run succeeds
        path = audio.write(ctx.staging / file_name, data, target_rate, params.format, params.bit_depth, params.bitrate)
        written.append(
            {
                "stem": label,
                "source": reference,
                "file": path.name,
                "format": params.format,
                "sample_rate": target_rate,
                "bit_depth": None if params.format == "mp3" else params.bit_depth,
            }
        )
        ctx.progress(name)((index + 1) / len(labels))
    return OpResult(info={"files": written})
