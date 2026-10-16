"""
Audio I/O. Everything in the engine is float32 with shape (channels, samples).

soundfile reads and writes the lossless formats directly; FFmpeg (as a
subprocess) decodes everything else and encodes MP3.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

EXPORT_FORMATS = ("flac", "wav", "mp3")
BIT_DEPTHS = (16, 24, 32)
MP3_BITRATES = ("128k", "192k", "256k", "320k")


class AudioError(Exception):
    """An audio file could not be read or written."""


def find_ffmpeg() -> str | None:
    """
    Locate FFmpeg: STEMLAB_FFMPEG (set by the packaged app, which ships its
    own binary), then the PATH, then the imageio-ffmpeg package if present.
    """
    override = os.environ.get("STEMLAB_FFMPEG")
    if override and Path(override).is_file():
        return override
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _require_ffmpeg() -> str:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise AudioError(
            "FFmpeg is needed for this file format but was not found. "
            "Install it or set STEMLAB_FFMPEG to its path."
        )
    return ffmpeg


def _ffmpeg(args: list[str], action: str) -> None:
    command = [_require_ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()[-3:]
        raise AudioError(f"FFmpeg could not {action}: " + " / ".join(detail))


def load(
    path: str | os.PathLike, sample_rate: int | None = None, channels: int | None = None
) -> tuple[np.ndarray, int]:
    """
    Read an audio file.

    Args:
        path: Any file soundfile or FFmpeg can decode (the audio track of a video too)
        sample_rate: Resample to this rate; None keeps the file's own
        channels: Convert to this many channels; None keeps the file's own

    Returns:
        (audio as float32 of shape (channels, samples), sample rate)
    """
    path = Path(path)
    if not path.is_file():
        raise AudioError(f"File not found: {path}")
    try:
        data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception:
        # Not a libsndfile format: let FFmpeg decode it to float WAV first
        with tempfile.TemporaryDirectory(prefix="stemlab_") as tmp:
            decoded = Path(tmp) / "decoded.wav"
            _ffmpeg(
                ["-i", str(path), "-vn", "-map", "0:a:0", "-c:a", "pcm_f32le", str(decoded)],
                f"read '{path.name}' as audio",
            )
            data, rate = sf.read(str(decoded), dtype="float32", always_2d=True)
    audio = np.ascontiguousarray(data.T)
    if audio.shape[1] == 0:
        raise AudioError(f"'{path.name}' contains no audio")
    if channels is not None:
        audio = to_channels(audio, channels)
    if sample_rate is not None and sample_rate != rate:
        audio = resample(audio, rate, sample_rate)
        rate = sample_rate
    return audio, rate


def info(path: str | os.PathLike) -> dict:
    """Sample rate, channels and duration of a file, without decoding all of it when possible."""
    try:
        meta = sf.info(str(path))
        return {
            "sample_rate": meta.samplerate,
            "channels": meta.channels,
            "duration": meta.frames / float(meta.samplerate),
        }
    except Exception:
        audio, rate = load(path)
        return {"sample_rate": rate, "channels": audio.shape[0], "duration": audio.shape[1] / float(rate)}


def to_channels(audio: np.ndarray, channels: int) -> np.ndarray:
    """Mono is duplicated, extra channels are dropped, stereo to mono is averaged."""
    current = audio.shape[0]
    if current == channels:
        return audio
    if channels == 1:
        return audio.mean(axis=0, keepdims=True).astype(np.float32)
    if current == 1:
        return np.repeat(audio, channels, axis=0)
    if current > channels:
        return np.ascontiguousarray(audio[:channels])
    return np.concatenate([audio, np.repeat(audio[-1:], channels - current, axis=0)], axis=0)


def resample(audio: np.ndarray, rate_from: int, rate_to: int) -> np.ndarray:
    """High quality sample rate conversion."""
    if rate_from == rate_to:
        return audio
    import soxr

    converted = soxr.resample(audio.T, rate_from, rate_to, quality="VHQ")
    return np.ascontiguousarray(converted.T, dtype=np.float32)


def match_length(audio: np.ndarray, length: int) -> np.ndarray:
    """Trim or zero-pad to an exact number of samples."""
    current = audio.shape[-1]
    if current == length:
        return audio
    if current > length:
        return audio[..., :length]
    return np.pad(audio, ((0, 0), (0, length - current)))


def write(
    path: str | os.PathLike,
    audio: np.ndarray,
    sample_rate: int,
    fmt: str = "flac",
    bit_depth: int = 24,
    bitrate: str = "320k",
) -> Path:
    """
    Write audio to a file. The extension of `path` is set to match `fmt`.

    Integer formats cannot hold samples beyond full scale, so those are
    clipped; 32-bit WAV is written as float and keeps them.
    """
    if fmt not in EXPORT_FORMATS:
        raise AudioError(f"Unsupported format '{fmt}' (use one of {', '.join(EXPORT_FORMATS)})")
    if bit_depth not in BIT_DEPTHS:
        raise AudioError(f"Unsupported bit depth {bit_depth} (use 16, 24 or 32)")
    path = Path(path)
    path = path.with_name(path.name + f".{fmt}") if path.suffix.lower() != f".{fmt}" else path
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = np.ascontiguousarray(audio.T)

    if fmt == "wav":
        subtype = {16: "PCM_16", 24: "PCM_24", 32: "FLOAT"}[bit_depth]
        if bit_depth != 32:
            frames = np.clip(frames, -1.0, 1.0)
        sf.write(str(path), frames, sample_rate, subtype=subtype, format="WAV")
    elif fmt == "flac":
        # FLAC has no float mode; 32 falls back to its largest integer depth
        subtype = "PCM_16" if bit_depth == 16 else "PCM_24"
        sf.write(str(path), np.clip(frames, -1.0, 1.0), sample_rate, subtype=subtype, format="FLAC")
    else:
        with tempfile.TemporaryDirectory(prefix="stemlab_") as tmp:
            source = Path(tmp) / "source.wav"
            sf.write(str(source), np.clip(frames, -1.0, 1.0), sample_rate, subtype="PCM_24", format="WAV")
            _ffmpeg(
                [
                    "-i",
                    str(source),
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    bitrate if bitrate in MP3_BITRATES else "320k",
                    str(path),
                ],
                f"write '{path.name}'",
            )
    return path


def file_sha256(path: str | os.PathLike) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def array_sha256(audio: np.ndarray, sample_rate: int) -> str:
    """Hash of audio content, used to key the cache of intermediate stems."""
    digest = hashlib.sha256()
    digest.update(f"{audio.shape}|{sample_rate}|".encode())
    digest.update(np.ascontiguousarray(audio, dtype=np.float32).tobytes())
    return digest.hexdigest()
