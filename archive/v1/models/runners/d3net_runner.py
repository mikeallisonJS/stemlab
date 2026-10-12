#!/usr/bin/env python3
"""
Runs D3Net music source separation inside its own environment.

Executed by the D3Net backend's Python, not by the application. It is based
on Sony's official NNabla implementation:
https://github.com/sony/ai-research-code/tree/master/d3net/music-source-separation

Setup downloads the network definition, the Wiener filter and the hyper
parameters from that repository at a pinned commit, together with the
pretrained weights, and converts the four networks to ONNX. NNabla itself
only runs single-threaded on the CPU (minutes per second of audio); ONNX
Runtime uses the GPU where it can and all CPU cores otherwise.

The overlap-add inference loop below follows upstream's util.py. Progress is
reported on stdout as "PROGRESS <percent>" / "STATUS <text>".
"""

import argparse
import hashlib
import os
import sys

TARGETS = ["vocals", "drums", "bass", "other"]

FFT_SIZE = 4096
HOP_SIZE = 1024
SAMPLE_RATE = 44100
# Frames filtered together by the multichannel Wiener filter (bounds memory use)
MWF_WINDOW = 1024

ONNX_DIR = "onnx"
ONNX_OPSET = "11"
# ONNX file format version matching opset 11
ONNX_IR_VERSION = 7
# Execution providers to try before falling back to the CPU
GPU_PROVIDERS = ["DmlExecutionProvider", "CUDAExecutionProvider"]

# The last upstream commit whose network definition matches the pretrained
# weights that are still being hosted (upstream later reworked its blocks)
SOURCE_COMMIT = "f7e22ae6bcfac525e7f14bd5517808d9ccb2a436"
SOURCE_URL = ("https://raw.githubusercontent.com/sony/ai-research-code/"
              f"{SOURCE_COMMIT}/d3net/music-source-separation/")
# File name -> SHA-256
SOURCE_FILES = {
    "model.py": "6b671167ec84b601736d547d423eeeef36418fa94bc381d5febfa9eac0f7934a",
    "filter.py": "71e6a814197ee5cbfb8e53539184cb5708f2bd152f4995441801942aa3d8a845",
    "configs/vocals.yaml": "a6c11f997db1845f23cdef5d2839a7d0b4c25730a4a5f04001eb64a660b129d4",
    "configs/drums.yaml": "73a021c45e985b4e665807a4652948aa4bc9ba23500cb5e0722a432ed8b2de96",
    "configs/bass.yaml": "4393cedfb883e67096278b0b6ac935999f7387e61ad9a678f4e49f816f874f07",
    "configs/other.yaml": "9d922188ff9cafa52044e0904a542e83e1c787f41cae85f2c24a6df886eaed0a",
}

WEIGHTS_FILE = "d3net-mss.h5"
WEIGHTS_SHA256 = "15467e03ba392c02b60954c9e8bd2f85e310251c4de303299cbe002fcd917495"
# Sony's original location first, then a mirror of the same file
WEIGHTS_URLS = [
    "https://nnabla.org/pretrained-models/ai-research-code/d3net/mss/d3net-mss.h5",
    "https://github.com/JeffreyCA/spleeterweb-d3net/releases/download/d3net-mss/d3net-mss.h5",
]


def report(percent, status=None):
    if status:
        print(f"STATUS {status}", flush=True)
    print(f"PROGRESS {percent:.1f}", flush=True)


# Setup ---------------------------------------------------------------------

def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, target, expected_sha256):
    """
    Download a file and verify its checksum. Returns False if the URL fails
    or serves something else, so the caller can try another location.
    """
    import ssl
    import urllib.request

    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()

    partial = target + ".part"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "CaptainStems"})
        with urllib.request.urlopen(request, context=context, timeout=60) as response, \
                open(partial, "wb") as f:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:
        print(f"Could not download {url}: {e}", flush=True)
        if os.path.exists(partial):
            os.remove(partial)
        return False

    actual = sha256_of(partial)
    if actual != expected_sha256:
        # An error page or a changed file: never use it
        os.remove(partial)
        print(f"Checksum mismatch for {url}\n  expected {expected_sha256}\n  got      {actual}", flush=True)
        return False
    os.replace(partial, target)
    return True


def load_hparams(data_dir, target):
    import yaml
    with open(os.path.join(data_dir, "src", "configs", f"{target}.yaml")) as f:
        return yaml.safe_load(f)


def export_onnx(data_dir, target):
    """Convert the pretrained NNabla network of one target to ONNX."""
    sys.path.insert(0, os.path.join(data_dir, "src"))
    import nnabla as nn
    import nnabla.utils.save as nnabla_save
    from nnabla.utils.converter.nnabla import NnpImporter
    from nnabla.utils.converter.onnx import OnnxExporter

    from model import d3_net

    onnx_dir = os.path.join(data_dir, ONNX_DIR)
    os.makedirs(onnx_dir, exist_ok=True)
    hparams = load_hparams(data_dir, target)

    # Keep only this target's parameters. grad_only=False includes the batch
    # normalization statistics.
    nn.load_parameters(os.path.join(data_dir, WEIGHTS_FILE))
    all_parameters = dict(nn.get_parameters(grad_only=False))
    nn.clear_parameters()
    for name, variable in all_parameters.items():
        if name.startswith(target + "/"):
            nn.parameter.set_parameter(name, variable)
    pretrained = set(nn.get_parameters(grad_only=False))

    x = nn.Variable((1, hparams["test_patch_len"], 2, FFT_SIZE // 2 + 1))
    with nn.parameter_scope(target):
        y = d3_net(x, hparams, test=True)

    # Building the network silently creates any parameter it does not find,
    # which would leave parts of it untrained
    created = set(nn.get_parameters(grad_only=False)) - pretrained
    if created or not pretrained:
        raise SystemExit(f"The pretrained weights do not match the {target} network "
                         f"({len(created)} parameters missing)")

    nnp_file = os.path.join(onnx_dir, f"{target}.nnp")
    nnabla_save.save(nnp_file, {
        "networks": [{"name": "net", "batch_size": 1, "outputs": {"y": y}, "names": {"x": x}}],
        "executors": [{"name": "runtime", "network": "net", "data": ["x"], "output": ["y"]}],
    })
    nnp = NnpImporter(nnp_file, expand_network=True, executor_index=True).execute()
    partial = os.path.join(onnx_dir, f"{target}.onnx.part")
    OnnxExporter(nnp, 1, ONNX_IR_VERSION, opset=ONNX_OPSET).execute(partial)
    os.replace(partial, os.path.join(onnx_dir, f"{target}.onnx"))
    os.remove(nnp_file)
    return 0


def setup(data_dir):
    """Download the D3Net sources and pretrained weights into data_dir and convert them."""
    source_dir = os.path.join(data_dir, "src")
    os.makedirs(os.path.join(source_dir, "configs"), exist_ok=True)

    for name, checksum in SOURCE_FILES.items():
        target = os.path.join(source_dir, *name.split("/"))
        if os.path.exists(target) and sha256_of(target) == checksum:
            continue
        print(f"Downloading {name}", flush=True)
        if not download(SOURCE_URL + name, target, checksum):
            raise SystemExit(f"Failed to download the D3Net source file {name}")

    weights = os.path.join(data_dir, WEIGHTS_FILE)
    if not (os.path.exists(weights) and sha256_of(weights) == WEIGHTS_SHA256):
        print("Downloading pretrained D3Net weights (45 MB)", flush=True)
        if not any(download(url, weights, WEIGHTS_SHA256) for url in WEIGHTS_URLS):
            raise SystemExit("Failed to download the pretrained D3Net weights")

    # One process per network: NNabla does not survive converting several in a row
    import subprocess
    for target in TARGETS:
        print(f"Converting the {target} network to ONNX", flush=True)
        result = subprocess.run([sys.executable, os.path.abspath(__file__),
                                 "--data", data_dir, "--export", target])
        if result.returncode != 0:
            raise SystemExit(f"Failed to convert the {target} network (exit code {result.returncode})")
    print("D3Net networks are ready", flush=True)
    return 0


# Signal processing -----------------------------------------------------------

def stft(signal, np, window):
    """STFT of a mono signal, centered with reflect padding. Returns frames x bins."""
    padded = np.pad(signal, FFT_SIZE // 2, mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, FFT_SIZE)[::HOP_SIZE]
    spectrum = np.empty((len(frames), FFT_SIZE // 2 + 1), dtype=np.complex64)
    for start in range(0, len(frames), 512):
        spectrum[start:start + 512] = np.fft.rfft(frames[start:start + 512] * window, axis=1)
    return spectrum


def istft(spectrum, length, np, window):
    """Inverse of stft(): overlap-add with squared window normalization."""
    n_frames = spectrum.shape[0]
    total = FFT_SIZE + HOP_SIZE * (n_frames - 1)
    signal = np.zeros(total, dtype=np.float64)
    weight = np.zeros(total, dtype=np.float64)
    window_sq = window.astype(np.float64) ** 2
    for start in range(0, n_frames, 512):
        chunk = np.fft.irfft(spectrum[start:start + 512], n=FFT_SIZE, axis=1) * window
        for offset, frame in enumerate(chunk):
            position = (start + offset) * HOP_SIZE
            signal[position:position + FFT_SIZE] += frame
            weight[position:position + FFT_SIZE] += window_sq
    signal /= np.where(weight > 1e-8, weight, 1.0)
    signal = signal[FFT_SIZE // 2:]
    if len(signal) < length:
        signal = np.pad(signal, (0, length - len(signal)))
    return signal[:length]


# Separation ------------------------------------------------------------------

def create_session(path, device):
    """Load a network, on the GPU when one is usable."""
    import onnxruntime as ort

    providers = []
    if device != "cpu":
        available = ort.get_available_providers()
        providers = [provider for provider in GPU_PROVIDERS if provider in available]

    options = ort.SessionOptions()
    options.log_severity_level = 3
    if "DmlExecutionProvider" in providers:
        # Required by the DirectML execution provider
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    if providers:
        try:
            return ort.InferenceSession(path, sess_options=options,
                                        providers=providers + ["CPUExecutionProvider"])
        except Exception as e:
            print(f"GPU not usable for D3Net, falling back to CPU: {e}", flush=True)
    return ort.InferenceSession(path, providers=["CPUExecutionProvider"])


def separate_target(session, magnitude, hparams, flip_average, on_patch, np):
    """
    Estimate the magnitude spectrogram of one target.

    Patches of the mixture are fed through the network with overlap and the
    overlapping outputs are averaged.
    """
    patch_length = hparams["test_patch_len"]
    shift = hparams["out_shift"]
    scale = patch_length // shift
    n_frames, n_channels, n_bins = magnitude.shape
    pad_end = patch_length - (n_frames % patch_length)
    patches = (n_frames + pad_end) // shift
    output_length = patches * shift + 2 * shift * (scale - 1)

    padded = np.concatenate([
        np.zeros([shift * (scale - 1), n_channels, n_bins], dtype=np.float32),
        magnitude,
        np.zeros([pad_end + shift * scale, n_channels, n_bins], dtype=np.float32),
    ], axis=0)
    output = np.zeros([output_length, n_channels, n_bins], dtype=np.float32)
    input_name = session.get_inputs()[0].name

    def predict(patch):
        return session.run(None, {input_name: np.ascontiguousarray(patch[np.newaxis])})[0][0]

    for patch_id in range(patches):
        patch = padded[patch_id * shift: patch_id * shift + patch_length]
        out = predict(patch)
        if flip_average:
            # Average the prediction with the one for swapped channels
            out = (out + predict(patch[:, ::-1, :])[:, ::-1, :]) * 0.5
        output[patch_id * shift: (patch_id + scale) * shift] += out[:shift * scale]
        on_patch(patch_id + 1, patches)

    return output[shift * (scale - 1): shift * (scale - 1) + n_frames] / scale


def separate(args):
    source_dir = os.path.join(args.data, "src")
    onnx_dir = os.path.join(args.data, ONNX_DIR)
    if not all(os.path.isfile(os.path.join(onnx_dir, f"{target}.onnx")) for target in TARGETS):
        raise SystemExit("D3Net is not set up completely. Reinstall the D3Net model.")
    sys.path.insert(0, source_dir)

    report(1, "Loading D3Net...")
    import numpy as np
    import soundfile as sf

    from filter import apply_mwf

    audio, sample_rate = sf.read(args.input, dtype="float32", always_2d=True)
    if sample_rate != SAMPLE_RATE:
        raise SystemExit(f"D3Net needs {SAMPLE_RATE} Hz audio, got {sample_rate} Hz")
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    audio = audio[:, :2]
    n_samples = len(audio)
    if n_samples < FFT_SIZE:
        audio = np.pad(audio, ((0, FFT_SIZE - n_samples), (0, 0)))

    # Periodic Hann window
    window = (0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(FFT_SIZE) / FFT_SIZE)).astype(np.float32)
    # frames x channels x bins
    mixture = np.stack([stft(audio[:, ch], np, window) for ch in range(2)], axis=1)
    magnitude = np.ascontiguousarray(np.abs(mixture))
    phase = np.exp(1j * np.angle(mixture)).astype(np.complex64)

    estimates = {}
    for index, target in enumerate(TARGETS):
        session = create_session(os.path.join(onnx_dir, f"{target}.onnx"), args.device)
        on_gpu = session.get_providers()[0] != "CPUExecutionProvider"
        print(f"STATUS Separating {target}" + ("..." if on_gpu else " (on the CPU, this is slow)..."),
              flush=True)

        def on_patch(done, total, index=index):
            report(4 + 82 * (index + done / total) / len(TARGETS))

        estimate = separate_target(session, magnitude, load_hparams(args.data, target),
                                   args.flip_average, on_patch, np)
        estimates[target] = (estimate * phase).astype(np.complex64)
        del session

    report(86, "Refining stems...")
    n_frames = mixture.shape[0]
    for start in range(0, n_frames, MWF_WINDOW):
        end = min(n_frames, start + MWF_WINDOW)
        filtered = apply_mwf({t: estimates[t][start:end] for t in TARGETS}, mixture[start:end])
        for target in TARGETS:
            estimates[target][start:end] = filtered[target]
        report(86 + 8 * end / n_frames)

    report(94, "Writing stems...")
    os.makedirs(args.output, exist_ok=True)
    for index, target in enumerate(TARGETS):
        channels = [istft(estimates[target][:, ch], n_samples, np, window) for ch in range(2)]
        data = np.clip(np.stack(channels, axis=1), -1.0, 1.0)
        sf.write(os.path.join(args.output, f"{target}.wav"), data, SAMPLE_RATE, subtype="PCM_16")
        report(94 + 6 * (index + 1) / len(TARGETS))
    return 0


def main():
    parser = argparse.ArgumentParser(description="Separate a WAV file with D3Net")
    parser.add_argument("--data", required=True, help="Directory holding the D3Net sources and weights")
    parser.add_argument("--setup", action="store_true", help="Download and convert the networks, then exit")
    parser.add_argument("--export", choices=TARGETS, help="Convert one network to ONNX, then exit")
    parser.add_argument("--input", help="16-bit 44.1 kHz stereo WAV file")
    parser.add_argument("--output", help="Directory for the separated stems")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"],
                        help="'cpu' disables GPU acceleration")
    parser.add_argument("--flip-average", action="store_true",
                        help="Average with the prediction for swapped channels (slower, better)")
    args = parser.parse_args()

    if args.setup:
        return setup(args.data)
    if args.export:
        return export_onnx(args.data, args.export)
    if not args.input or not args.output:
        parser.error("--input and --output are required")
    return separate(args)


if __name__ == "__main__":
    sys.exit(main())
