"""
Installs the GPU-specific half of the environment.

torch, the model libraries built on it and onnxruntime are not declared in
pyproject.toml, because which build is right depends on the machine. This
module works out the commands for the detected (or overridden) flavor and runs
them with uv. The packaged app calls the same code on first run.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable

from captainstems.backends import device

# Verified with the bundled backends
TORCH_SPEC = "torch>=2.6,<2.15"

# What the backends import at inference time. MSST's own requirements.txt also
# covers training (wandb, audiomentations, a GUI toolkit) and pins versions
# that conflict with current torch, so the inference subset is listed here.
BACKEND_PACKAGES = [
    "demucs==4.1.0",
    "einops",
    "rotary-embedding-torch",
    "beartype",
    "ml_collections",
    "omegaconf",
    "librosa",
    "tqdm",
    "huggingface-hub",
    # Needed by some MSST architectures only: htdemucs, bandit
    "openunmix",
    "pytorch-lightning",
]


def onnxruntime_package(flavor: str) -> str:
    """onnxruntime's wheels are per provider and conflict; exactly one is installed."""
    if flavor == "cuda":
        return "onnxruntime-gpu"
    if sys.platform == "win32":
        # DirectML runs on any DirectX 12 GPU and includes the CPU provider
        return "onnxruntime-directml"
    return "onnxruntime"


def installer() -> list[str]:
    """The command prefix that installs into the running environment."""
    uv = shutil.which("uv")
    if uv:
        return [uv, "pip", "install", "--python", sys.executable]
    return [sys.executable, "-m", "pip", "install"]


def plan(flavor: str) -> list[list[str]]:
    """The exact commands a bootstrap for this flavor runs, in order."""
    if flavor not in device.FLAVORS:
        raise ValueError(f"unknown flavor '{flavor}' (use one of {', '.join(device.FLAVORS)})")
    base = installer()
    # torchaudio must come from the same index to match the torch build
    torch_command = [*base, TORCH_SPEC, "torchaudio"]
    index = device.TORCH_INDEX[flavor]
    if index:
        torch_command += ["--index-url", index]
    return [
        torch_command,
        [*base, *BACKEND_PACKAGES],
        [*base, onnxruntime_package(flavor)],
    ]


def run(flavor: str, log: Callable[[str], None] = print) -> bool:
    """Run the bootstrap. Returns False at the first command that fails."""
    for command in plan(flavor):
        log("$ " + " ".join(command))
        result = subprocess.run(command)
        if result.returncode != 0:
            log(f"Command failed with exit code {result.returncode}")
            return False
    return True
