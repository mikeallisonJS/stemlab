"""Audio helpers for the user interface."""

import math

import numpy as np
import soundfile as sf


def compute_peaks(path, buckets: int = 1600) -> np.ndarray:
    """
    Reduce an audio file to a min/max envelope for drawing a waveform.

    The file is read in blocks, so memory use stays small for long tracks.

    Args:
        path: Path to an audio file readable by libsndfile
        buckets: Approximate number of envelope points to produce

    Returns:
        float32 array of shape (n, 2) holding (minimum, maximum) per bucket
    """
    with sf.SoundFile(str(path)) as f:
        total = len(f)
        if total <= 0:
            return np.zeros((0, 2), dtype=np.float32)
        per_bucket = max(1, math.ceil(total / max(1, buckets)))
        mins, maxs = [], []
        carry_min = carry_max = None
        for block in f.blocks(blocksize=per_bucket * 256, dtype="float32", always_2d=True):
            low = block.min(axis=1)
            high = block.max(axis=1)
            if carry_min is not None:
                low = np.concatenate([carry_min, low])
                high = np.concatenate([carry_max, high])
                carry_min = carry_max = None
            whole = len(low) // per_bucket
            if whole:
                mins.append(low[: whole * per_bucket].reshape(whole, per_bucket).min(axis=1))
                maxs.append(high[: whole * per_bucket].reshape(whole, per_bucket).max(axis=1))
            if len(low) > whole * per_bucket:
                carry_min = low[whole * per_bucket:]
                carry_max = high[whole * per_bucket:]
        if carry_min is not None:
            mins.append(np.array([carry_min.min()], dtype=np.float32))
            maxs.append(np.array([carry_max.max()], dtype=np.float32))
    if not mins:
        return np.zeros((0, 2), dtype=np.float32)
    return np.stack([np.concatenate(mins), np.concatenate(maxs)], axis=1).astype(np.float32)


def format_time(seconds) -> str:
    """Format a duration as m:ss (or h:mm:ss for long audio)."""
    if seconds is None or seconds < 0:
        return "--:--"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
