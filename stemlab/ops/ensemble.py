"""ensemble: combine several versions of the same stem."""

from __future__ import annotations

import numpy as np

from stemlab import audio, dsp
from stemlab.ops import OpResult


def combine(inputs: list[np.ndarray], method: str, weights: list[float] | None = None) -> np.ndarray:
    """
    Combine equally shaped signals.

    avg       weighted mean of the waveforms
    median    per-sample median of the waveforms
    max_spec  per time-frequency bin, the input with the largest magnitude
    min_spec  per time-frequency bin, the input with the smallest magnitude
    """
    stacked = np.stack(inputs, axis=0)  # (inputs, channels, samples)
    if method == "avg":
        if weights is None:
            return stacked.mean(axis=0).astype(np.float32)
        w = np.asarray(weights, dtype=np.float32)
        return np.tensordot(w / w.sum(), stacked, axes=1).astype(np.float32)
    if method == "median":
        return np.median(stacked, axis=0).astype(np.float32)
    if method not in ("max_spec", "min_spec"):
        raise ValueError(f"unknown ensemble method '{method}'")

    length = stacked.shape[-1]
    out = np.empty(stacked.shape[1:], dtype=np.float32)
    for channel in range(stacked.shape[1]):
        spectra = np.stack([dsp.stft(signal[channel]) for signal in stacked], axis=0)  # (inputs, frames, bins)
        magnitudes = np.abs(spectra)
        pick = magnitudes.argmax(axis=0) if method == "max_spec" else magnitudes.argmin(axis=0)
        chosen = np.take_along_axis(spectra, pick[np.newaxis], axis=0)[0]
        out[channel] = dsp.istft(chosen, length)
    return out


def run(ctx, name: str, node, plan) -> OpResult:
    signals = [ctx.audio(reference) for reference in node.inputs]
    first = signals[0]
    aligned = [first] + [
        audio.match_length(audio.to_channels(signal, first.shape[0]), first.shape[-1]) for signal in signals[1:]
    ]
    out = combine(aligned, node.params.method, node.params.weights)
    np.nan_to_num(out, copy=False)
    return OpResult(stems={"out": out})
