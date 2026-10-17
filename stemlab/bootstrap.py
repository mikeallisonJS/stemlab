"""
Installs the GPU-specific half of the environment.

torch, the model libraries built on it and onnxruntime are not declared in
pyproject.toml, because which build is right depends on the machine. This
module works out the commands for the detected (or overridden) flavor and runs
them with uv. The packaged app calls the same code on first run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable

from stemlab.backends import device

# Verified with the bundled backends
TORCH_VERSION = ">=2.6,<2.15"
TORCH_SPEC = "torch" + TORCH_VERSION

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
        # Builds up to 1.23 use CUDA 12, whose libraries come with the torch build above.
        # Later ones need CUDA 13 and would find no cuDNN.
        return "onnxruntime-gpu>=1.20,<1.24"
    if sys.platform == "win32":
        # DirectML runs on any DirectX 12 GPU and includes the CPU provider
        return "onnxruntime-directml"
    return "onnxruntime"


def installer() -> list[str]:
    """
    The command prefix that installs into the running environment: uv when there
    is one (the packaged app names its own in STEMLAB_UV), else pip.
    """
    uv = os.environ.get("STEMLAB_UV") or shutil.which("uv")
    if uv:
        return [uv, "pip", "install", "--python", sys.executable]
    return [sys.executable, "-m", "pip", "install"]


def reinstall_flags() -> list[str]:
    """
    Replace an installed torch even when its version already satisfies the spec:
    between flavors the version stays and the build (CPU, CUDA, ROCm) changes.
    """
    if shutil.which("uv"):
        return ["--reinstall-package", "torch", "--reinstall-package", "torchaudio"]
    return ["--force-reinstall"]


def torch_requirement(flavor: str) -> str:
    """torch, with the extra that picks AMD's build for the GPU target on Windows ROCm."""
    if flavor == "rocm" and sys.platform == "win32":
        target = device.rocm_target()
        if not target:
            raise ValueError(
                "ROCm on Windows needs the GPU target AMD builds its wheels for, and this GPU is not "
                "in the list of known ones. Set it with `stemlab doctor --set-rocm-target gfx1151` "
                "(gfx1151: Ryzen AI Max, gfx1150: Ryzen AI 300, gfx110X: RX 7000, gfx120X: RX 9000)."
            )
        return f"torch[device-{target}]{TORCH_VERSION}"
    return TORCH_SPEC


def plan(flavor: str) -> list[list[str]]:
    """The exact commands a bootstrap for this flavor runs, in order."""
    if flavor not in device.FLAVORS:
        raise ValueError(f"unknown flavor '{flavor}' (use one of {', '.join(device.FLAVORS)})")
    base = installer()
    # torchaudio must come from the same index to match the torch build
    torch_command = [*base, *reinstall_flags(), torch_requirement(flavor), "torchaudio"]
    index = device.torch_index(flavor)
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
