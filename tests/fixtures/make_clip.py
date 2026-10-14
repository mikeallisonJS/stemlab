"""
Generates tests/fixtures/clip-5s.flac: a 5 second synthetic stereo mix.

The clip is made from scratch (noise bursts on a beat, a bass tone, a wobbling
lead), so it carries no third-party rights. Run this again only if the
fixture needs to change; tests depend on its exact length.
"""

from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 44100
SECONDS = 5


def main() -> None:
    t = np.arange(SAMPLE_RATE * SECONDS) / SAMPLE_RATE
    rng = np.random.default_rng(1234)

    bass = 0.22 * np.sin(2 * np.pi * 55.0 * t)
    drums = np.zeros_like(t)
    for beat in np.arange(0, SECONDS, 0.5):
        start = int(beat * SAMPLE_RATE)
        length = int(0.06 * SAMPLE_RATE)
        drums[start : start + length] += 0.45 * rng.standard_normal(length) * np.linspace(1, 0, length) ** 2
    lead = 0.18 * np.sin(2 * np.pi * (440.0 * t + 12.0 * np.sin(2 * np.pi * 0.7 * t)))

    left = bass + drums + 0.8 * lead
    right = bass + 0.9 * drums + lead
    data = np.stack([left, right], axis=1).astype(np.float32)
    data *= 0.9 / np.abs(data).max()

    target = Path(__file__).with_name("clip-5s.flac")
    sf.write(str(target), data, SAMPLE_RATE, subtype="PCM_16", format="FLAC")
    print(f"wrote {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
