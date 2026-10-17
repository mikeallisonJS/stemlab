"""analyze: residual = mix - sum(stems), with levels and an optional SI-SDR score."""

from __future__ import annotations

import numpy as np

from stemlab import audio, dsp
from stemlab.ops import OpResult


def run(ctx, name: str, node, plan) -> OpResult:
    mix = ctx.audio(node.inputs.mix)
    total = np.zeros_like(mix)
    stems = {}
    for reference in node.inputs.stems:
        stem = audio.match_length(audio.to_channels(ctx.audio(reference), mix.shape[0]), mix.shape[-1])
        stems[reference] = {"rms_db": round(dsp.rms_db(stem), 2), "peak_db": round(dsp.peak_db(stem), 2)}
        total += stem
    residual = (mix - total).astype(np.float32)

    mix_rms = dsp.rms_db(mix)
    residual_rms = dsp.rms_db(residual)
    metrics = {
        "mix_rms_db": round(mix_rms, 2),
        "residual_rms_db": round(residual_rms, 2),
        # How far below the mix the lost signal sits; more negative is better
        "residual_vs_mix_db": round(residual_rms - mix_rms, 2),
        "residual_peak_db": round(dsp.peak_db(residual), 2),
        "stems": stems,
    }

    if node.params.reference:
        reference_audio, _ = audio.load(ctx.resolve_path(node.params.reference), sample_rate=ctx.sample_rate)
        first = node.inputs.stems[0]
        estimate = ctx.audio(first)
        reference_audio = audio.to_channels(reference_audio, estimate.shape[0])
        metrics["si_sdr_db"] = round(dsp.si_sdr(estimate, reference_audio), 2)
        metrics["si_sdr_stem"] = first
        metrics["reference"] = str(node.params.reference)

    return OpResult(stems={"residual": residual}, info={"metrics": metrics})
