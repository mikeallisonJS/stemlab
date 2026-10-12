#!/usr/bin/env python3
"""
Runs Spleeter inside its own environment.

Executed by the Spleeter backend's Python, not by the application. Audio is
read and written with soundfile, so no FFmpeg binary is needed here.
Progress is reported on stdout as "PROGRESS <percent>" / "STATUS <text>".
"""

import argparse
import os
import sys


def report(percent, status=None):
    if status:
        print(f"STATUS {status}", flush=True)
    print(f"PROGRESS {percent}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Separate a WAV file with Spleeter")
    parser.add_argument("--input", required=True, help="16-bit 44.1 kHz stereo WAV file")
    parser.add_argument("--output", required=True, help="Directory for the separated stems")
    parser.add_argument("--model", default="2stems", choices=["2stems", "4stems", "5stems"])
    parser.add_argument("--weights", required=True, help="Directory for the pretrained models")
    parser.add_argument("--mwf", action="store_true", help="Use multichannel Wiener filtering")
    args = parser.parse_args()

    # Must be set before spleeter is imported
    os.environ["MODEL_PATH"] = args.weights
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

    report(2, "Loading Spleeter...")
    import numpy as np
    import soundfile as sf
    from spleeter.separator import Separator

    waveform, sample_rate = sf.read(args.input, dtype="float32", always_2d=True)
    if waveform.shape[1] == 1:
        waveform = np.repeat(waveform, 2, axis=1)

    if not os.path.isdir(os.path.join(args.weights, args.model)):
        report(8, "Downloading model weights...")
    separator = Separator(f"spleeter:{args.model}", MWF=args.mwf, multiprocess=False)

    report(15, "Separating stems...")
    prediction = separator.separate(waveform)

    report(90, "Writing stems...")
    os.makedirs(args.output, exist_ok=True)
    for instrument, data in prediction.items():
        data = np.clip(data, -1.0, 1.0)
        sf.write(os.path.join(args.output, f"{instrument}.wav"), data, sample_rate, subtype="PCM_16")
    report(100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
