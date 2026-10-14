"""Hardware detection: which GPU is present and which torch build fits it."""

from __future__ import annotations

import functools
import json
import platform
import re
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

# pytorch.org has no ROCm build for Windows. AMD publishes its own, compiled per
# GPU target: `torch[device-<target>]` from this index installs torch together
# with the HIP runtime and the libraries for that target.
ROCM_WINDOWS_INDEX = "https://stable.repo.amd.com/rocm/whl-next/"

# Adapter name on Windows (a regular expression on the driver's description) ->
# the target AMD builds Windows wheels for. Only GPUs AMD lists for ROCm on Windows.
ROCM_WINDOWS_TARGETS = (
    (r"Radeon(\(TM\))? 80[46]0S", "gfx1151"),  # Ryzen AI Max (Strix Halo)
    (r"Radeon(\(TM\))? 8[89]0M", "gfx1150"),  # Ryzen AI 300 (Strix Point)
    (r"Radeon RX 7[67]00[SM]", "gfx1102"),  # Navi 33 mobile
    (r"Radeon RX 76\d0", "gfx1102"),  # Navi 33: RX 7600, 7600 XT, 7650 GRE
    (r"Radeon RX 7[78]\d0", "gfx1101"),  # Navi 32: RX 7700 XT, 7800 XT, 7800M
    (r"Radeon RX 79\d0", "gfx1100"),  # Navi 31: RX 7900 series, 7900M
    (r"Radeon RX 9070", "gfx1201"),  # Navi 48
    (r"Radeon RX 9060", "gfx1200"),  # Navi 44
)


def torch_index(flavor: str) -> str | None:
    """Where the torch wheels for a flavor come from on this platform."""
    if flavor == "rocm" and sys.platform == "win32":
        return ROCM_WINDOWS_INDEX
    return TORCH_INDEX[flavor]


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
    nvidia-smi -> CUDA; rocminfo on Linux -> ROCm; a supported AMD GPU on Windows -> ROCm;
    arm64 macOS -> MPS; else CPU.

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

    if sys.platform == "win32":
        found = _windows_amd_gpu()
        if found:
            name, memory, target = found
            # Without a target AMD builds Windows wheels for, torch stays on the CPU
            # (onnxruntime still uses the GPU through DirectML)
            return ("rocm" if target else "cpu"), name, memory

    if sys.platform == "darwin" and platform.machine() == "arm64":
        return "mps", "Apple Silicon", None

    return "cpu", None, None


@functools.lru_cache(maxsize=1)
def _windows_display_adapters() -> list[dict]:
    """
    The display adapters Windows knows, from the registry's display class: name, PCI
    id and dedicated memory. Needs no vendor tool, which AMD does not ship for ROCm.
    """
    import winreg

    adapters = []
    display_class = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, display_class) as root:
            for index in range(256):
                try:
                    subkey = winreg.EnumKey(root, index)
                except OSError:
                    break
                if not subkey.isdigit():
                    continue
                try:
                    with winreg.OpenKey(root, subkey) as adapter:
                        name = winreg.QueryValueEx(adapter, "DriverDesc")[0]
                        try:
                            pci = winreg.QueryValueEx(adapter, "MatchingDeviceId")[0]
                        except OSError:
                            pci = ""
                        try:
                            memory = winreg.QueryValueEx(adapter, "HardwareInformation.qwMemorySize")[0]
                        except OSError:
                            memory = None
                except OSError:
                    continue
                if isinstance(memory, bytes):
                    memory = int.from_bytes(memory, "little")
                adapters.append({"name": str(name), "pci": str(pci).lower(), "memory": memory})
    except OSError:
        pass
    return adapters


def _windows_amd_gpu() -> tuple[str, int | None, str | None] | None:
    """The AMD GPU on Windows as (name, VRAM in MiB, ROCm target); None without one."""
    amd = [a for a in _windows_display_adapters() if "ven_1002" in a["pci"]]
    if not amd:
        return None
    gpu = max(amd, key=lambda a: a["memory"] or 0)
    memory = int(gpu["memory"] // (1024 * 1024)) if gpu["memory"] else None
    return gpu["name"], memory, rocm_target_for(gpu["name"])


def rocm_target_for(name: str) -> str | None:
    """The target AMD's Windows wheels are built for, from the adapter name."""
    for pattern, target in ROCM_WINDOWS_TARGETS:
        if re.search(pattern, name):
            return target
    return None


def rocm_target() -> str | None:
    """The ROCm target to install for: the configured one, else the detected one (Windows only)."""
    override = read_config().get("rocm_target")
    if override:
        return str(override)
    if sys.platform == "win32":
        found = _windows_amd_gpu()
        return found[2] if found else None
    return None


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
    state = {"version": None, "hip": None, "cuda": False, "mps": False, "device_name": None}
    try:
        import torch
    except ImportError:
        return state
    state["version"] = torch.__version__
    # ROCm builds report themselves as CUDA; this is how to tell them apart
    state["hip"] = getattr(torch.version, "hip", None)
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
    rocm_target: str | None = None
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
        torch_index=torch_index(flavor),
        rocm_target=rocm_target() if flavor == "rocm" else None,
        torch=torch_state(),
        onnxruntime=onnx_state(),
        ffmpeg=audio.find_ffmpeg(),
        home=str(paths.home()),
        backends=base.backend_versions(),
    )
