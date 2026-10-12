"""Signal processing helpers written with NumPy only, so the engine core needs no torch."""

from __future__ import annotations

import struct
import zlib

import numpy as np

N_FFT = 2048
HOP = 512  # 75% overlap: a Hann window sums to a constant, so the inverse is exact


def _window(n_fft: int) -> np.ndarray:
    # Periodic Hann
    return (0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(n_fft) / n_fft)).astype(np.float32)


def stft(signal: np.ndarray, n_fft: int = N_FFT, hop: int = HOP) -> np.ndarray:
    """STFT of a mono signal, centered with reflect padding. Returns (frames, bins) complex64."""
    signal = np.asarray(signal, dtype=np.float32)
    pad = n_fft // 2
    if len(signal) <= pad:
        signal = np.pad(signal, (0, pad + 1 - len(signal)))
    padded = np.pad(signal, pad, mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, n_fft)[::hop]
    window = _window(n_fft)
    spectrum = np.empty((len(frames), n_fft // 2 + 1), dtype=np.complex64)
    for start in range(0, len(frames), 1024):
        spectrum[start : start + 1024] = np.fft.rfft(frames[start : start + 1024] * window, axis=1)
    return spectrum


def istft(spectrum: np.ndarray, length: int, n_fft: int = N_FFT, hop: int = HOP) -> np.ndarray:
    """Inverse of `stft`: overlap-add with squared-window normalization, trimmed to `length`."""
    n_frames = spectrum.shape[0]
    total = n_fft + hop * (n_frames - 1)
    signal = np.zeros(total, dtype=np.float64)
    weight = np.zeros(total, dtype=np.float64)
    window = _window(n_fft).astype(np.float64)
    window_sq = window**2
    for start in range(0, n_frames, 1024):
        chunk = np.fft.irfft(spectrum[start : start + 1024], n=n_fft, axis=1) * window
        for offset, frame in enumerate(chunk):
            position = (start + offset) * hop
            signal[position : position + n_fft] += frame
            weight[position : position + n_fft] += window_sq
    signal /= np.where(weight > 1e-8, weight, 1.0)
    signal = signal[n_fft // 2 :]
    if len(signal) < length:
        signal = np.pad(signal, (0, length - len(signal)))
    return signal[:length].astype(np.float32)


def rms_db(audio: np.ndarray) -> float:
    """RMS level in dBFS; -inf is reported as -120."""
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64)))) if audio.size else 0.0
    return max(-120.0, 20.0 * np.log10(rms)) if rms > 0 else -120.0


def peak_db(audio: np.ndarray) -> float:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    return max(-120.0, 20.0 * np.log10(peak)) if peak > 0 else -120.0


def si_sdr(estimate: np.ndarray, reference: np.ndarray) -> float:
    """Scale-invariant signal-to-distortion ratio in dB, over all channels together."""
    length = min(estimate.shape[-1], reference.shape[-1])
    estimate = estimate[..., :length].astype(np.float64).ravel()
    reference = reference[..., :length].astype(np.float64).ravel()
    reference_energy = float(np.dot(reference, reference))
    if reference_energy <= 0:
        return float("-inf")
    target = (float(np.dot(estimate, reference)) / reference_energy) * reference
    noise = estimate - target
    noise_energy = float(np.dot(noise, noise))
    if noise_energy <= 0:
        return float("inf")
    return 10.0 * np.log10(float(np.dot(target, target)) / noise_energy)


def peaks(audio: np.ndarray, buckets: int = 2000) -> list[list[float]]:
    """Min/max envelope of the mono mixdown, for drawing a waveform: [[min, max], ...]."""
    mono = audio.mean(axis=0) if audio.ndim == 2 else audio
    if mono.size == 0:
        return []
    buckets = max(1, min(buckets, mono.size))
    edges = np.linspace(0, mono.size, buckets + 1).astype(int)[:-1]
    low = np.minimum.reduceat(mono, edges)
    high = np.maximum.reduceat(mono, edges)
    return np.stack([low, high], axis=1).astype(np.float64).round(4).tolist()


# Spectrogram images --------------------------------------------------------------


def _colormap() -> np.ndarray:
    """A 256 entry dark-to-bright colormap (black, purple, orange, pale yellow)."""
    stops = np.array(
        [
            [0, 0, 4],
            [40, 11, 84],
            [101, 21, 110],
            [159, 42, 99],
            [212, 72, 66],
            [245, 125, 21],
            [250, 193, 39],
            [252, 255, 164],
        ],
        dtype=np.float32,
    )
    positions = np.linspace(0, 255, len(stops))
    index = np.arange(256)
    return np.stack([np.interp(index, positions, stops[:, channel]) for channel in range(3)], axis=1).astype(np.uint8)


def spectrogram_image(
    audio: np.ndarray, sample_rate: int, width: int = 1200, height: int = 256, floor_db: float = -100.0
) -> np.ndarray:
    """
    Log-frequency magnitude spectrogram of the mono mixdown as an RGB image.

    Returns:
        uint8 array of shape (height, width, 3); low frequencies at the bottom
    """
    mono = audio.mean(axis=0) if audio.ndim == 2 else audio
    spectrum = np.abs(stft(mono))  # (frames, bins)
    if spectrum.shape[0] == 0:
        return np.zeros((height, width, 3), dtype=np.uint8)

    # Time: reduce frames to `width` columns by taking the maximum in each
    edges = np.linspace(0, spectrum.shape[0], width + 1).astype(int)
    starts = np.minimum(edges[:-1], spectrum.shape[0] - 1)
    columns = np.maximum.reduceat(spectrum, starts, axis=0)  # (width, bins)

    # Frequency: log spaced rows from 30 Hz to Nyquist
    nyquist = sample_rate / 2.0
    frequencies = np.geomspace(30.0, nyquist, height)
    bins = np.clip(frequencies / nyquist * (spectrum.shape[1] - 1), 0, spectrum.shape[1] - 1)
    lower = np.floor(bins).astype(int)
    upper = np.minimum(lower + 1, spectrum.shape[1] - 1)
    fraction = (bins - lower).astype(np.float32)
    rows = columns[:, lower] * (1 - fraction) + columns[:, upper] * fraction  # (width, height)

    reference = N_FFT / 4.0  # magnitude of a full-scale sine with a Hann window
    decibels = 20.0 * np.log10(np.maximum(rows / reference, 1e-10))
    scaled = np.clip((decibels - floor_db) / -floor_db, 0.0, 1.0)
    image = _colormap()[(scaled * 255).astype(np.uint8)]  # (width, height, 3)
    return np.ascontiguousarray(image.transpose(1, 0, 2)[::-1])


def png_bytes(image: np.ndarray) -> bytes:
    """Encode an RGB uint8 image as PNG without an imaging library."""
    height, width, _ = image.shape
    raw = b"".join(b"\x00" + image[row].tobytes() for row in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
