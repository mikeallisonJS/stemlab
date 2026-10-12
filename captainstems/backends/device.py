"""Hardware detection: which GPU is present and which torch build fits it."""

from __future__ import annotations

import functools
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field

from captainstems import paths

FLAVORS = ("cuda", "rocm", "mps", "cpu")

# Where each flavor's torch wheels come from. None means the default index (PyPI).
TORCH_INDEX = {
    "cuda": "https://download.pytorch.org/whl/cu126",
    "rocm": "https://download.pytorch.org/whl/rocm6.3",
    "mps": None,
    "cpu": "https://download.pytorch.org/whl/cpu",
}


def _run(command: list[str], timeout: int = 15) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


@functools.lru_cache(maxsize=1)
def detect_gpu() -> tuple[str, str | None, int | None]:
    """
    Detect the GPU flavor in the order the handoff fixes:
    nvidia-smi -> CUDA; rocminfo on Linux -> ROCm; arm64 macOS -> MPS; else CPU.

    Returns:
        (flavor, GPU name, VRAM in MiB), the last two None when unknown
    """
    if shutil.which("nvidia-smi"):
        out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
        if out and out.strip():
            name, _, memory = out.strip().splitlines()[0].rpartition(",")
            try:
                return "cuda", name.strip(), int(float(memory))
            except ValueError:
                return "cuda", name.strip() or None, None

    if sys.platform.startswith("linux") and shutil.which("rocminfo"):
        if _run(["rocminfo"]) is not None:
            return "rocm", "AMD GPU (ROCm)", None

    if sys.platform == "darwin" and platform.machine() == "arm64":
        return "mps", "Apple Silicon", None

    return "cpu", None, None


def read_config() -> dict:
    try:
        data = json.loads(paths.config_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_config(**values) -> dict:
    config = read_config()
    config.update(values)
    paths.config_file().write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def chosen_flavor() -> tuple[str, str]:
    """The torch flavor to use and where the choice came from ("override" or "detected")."""
    override = read_config().get("torch_flavor")
    if override in FLAVORS:
        return override, "override"
    return detect_gpu()[0], "detected"


def torch_state() -> dict:
    """What the installed torch can do. Empty values when torch is not installed."""
    state = {"version": None, "cuda": False, "mps": False, "device_name": None}
    try:
        import torch
    except ImportError:
        return state
    state["version"] = torch.__version__
    try:
        state["cuda"] = bool(torch.cuda.is_available())
        if state["cuda"]:
            state["device_name"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    try:
        state["mps"] = bool(torch.backends.mps.is_available())
    except Exception:
        pass
    return state


def onnx_state() -> dict:
    try:
        import onnxruntime as ort
    except ImportError:
        return {"version": None, "providers": []}
    return {"version": ort.__version__, "providers": list(ort.get_available_providers())}


def resolve_device(requested: str = "auto") -> str:
    """
    Turn a device request into one torch can use right now.

    "auto" picks the best available. An explicit request for a device that is
    missing is an error rather than a silent fallback to something slower.
    """
    state = torch_state()
    if requested in ("auto", None, ""):
        if state["cuda"]:
            return "cuda"
        if state["mps"]:
            return "mps"
        return "cpu"
    if requested == "cuda" and not state["cuda"]:
        raise RuntimeError("device 'cuda' was requested, but the installed torch has no CUDA support")
    if requested == "mps" and not state["mps"]:
        raise RuntimeError("device 'mps' was requested, but torch reports no MPS device")
    if requested not in ("cuda", "mps", "cpu") and not requested.startswith("cuda:"):
        raise ValueError(f"unknown device '{requested}'")
    return requested


def resolve_dtype(requested: str, device: str) -> str:
    """fp16 by default on CUDA only: half precision on MPS is unreliable for RoFormer attention."""
    if requested in ("auto", None, ""):
        return "fp16" if device.startswith("cuda") else "fp32"
    if requested not in ("fp16", "fp32"):
        raise ValueError(f"unknown dtype '{requested}' (use fp16, fp32 or auto)")
    return requested


def device_defaults(device: str, vram_mb: int | None = None) -> dict:
    """
    Starting inference parameters per device (handoff table, tuned in Phase 1).
    Explicit params in a recipe or a model manifest always win over these.
    """
    if device.startswith("cuda"):
        if vram_mb is None or vram_mb >= 12000:
            return {"dtype": "fp16", "chunk_size": 352800, "overlap": 4, "batch_size": 4}
        return {"dtype": "fp16", "chunk_size": 352800, "overlap": 2, "batch_size": 1}
    if device == "mps":
        return {"dtype": "fp32", "chunk_size": 352800, "overlap": 2, "batch_size": 1}
    return {"dtype": "fp32", "chunk_size": 176400, "overlap": 2, "batch_size": 1}


def vram_mb() -> int | None:
    return detect_gpu()[2]


@dataclass
class SystemInfo:
    """Everything `doctor` and GET /system report."""

    os: str
    os_version: str
    machine: str
    python: str
    gpu: str | None
    vram_mb: int | None
    detected_flavor: str
    flavor: str
    flavor_source: str
    torch_index: str | None
    torch: dict = field(default_factory=dict)
    onnxruntime: dict = field(default_factory=dict)
    ffmpeg: str | None = None
    home: str = ""
    backends: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def system_info() -> SystemInfo:
    from captainstems import audio
    from captainstems.backends import base

    detected, gpu, memory = detect_gpu()
    flavor, source = chosen_flavor()
    return SystemInfo(
        os=platform.system(),
        os_version=platform.version(),
        machine=platform.machine(),
        python=platform.python_version(),
        gpu=gpu,
        vram_mb=memory,
        detected_flavor=detected,
        flavor=flavor,
        flavor_source=source,
        torch_index=TORCH_INDEX[flavor],
        torch=torch_state(),
        onnxruntime=onnx_state(),
        ffmpeg=audio.find_ffmpeg(),
        home=str(paths.home()),
        backends=base.backend_versions(),
    )
