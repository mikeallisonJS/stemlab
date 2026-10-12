"""
Isolated Python environments for model backends.

The separation libraries pin mutually incompatible versions of NumPy,
PyTorch and TensorFlow, so each backend gets its own virtual environment
below the application data directory. Installing a model never touches the
environment the application itself runs in, and uninstalling one is simply
deleting its directory.
"""

import functools
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from core import ffmpeg, paths
from core.process import ProcessCancelled, child_env, run_streaming, subprocess_flags

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_APPLE_SILICON = IS_MACOS and platform.machine() == "arm64"

MARKER_FILE = "captainstems.json"

# PyTorch builds verified with the bundled backends
TORCH_SPEC = "torch>=2.3,<2.15"
TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu126"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"

LogCallback = Optional[Callable[[str], None]]


class EnvError(Exception):
    """Raised when a backend environment cannot be created or used."""


@functools.lru_cache(maxsize=1)
def has_nvidia_gpu() -> bool:
    """Whether an NVIDIA GPU with a working driver is present."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False
    try:
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=15,
            **subprocess_flags(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def torch_install_args() -> Optional[List[str]]:
    """
    pip arguments that install the right PyTorch build for this machine, or
    None when the default build from PyPI is the right one (macOS).
    """
    if IS_MACOS:
        return None
    index = TORCH_CUDA_INDEX if has_nvidia_gpu() else TORCH_CPU_INDEX
    return [TORCH_SPEC, "--index-url", index]


def _interpreter_version(command: Sequence[str]) -> Optional[Tuple[int, int]]:
    try:
        result = subprocess.run(
            list(command) + ["-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=30,
            **subprocess_flags(),
        )
        major, minor = result.stdout.split()
        return int(major), int(minor)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _base_python() -> str:
    """The interpreter running the application (never pythonw)."""
    executable = Path(sys.executable)
    if IS_WINDOWS and executable.name.lower() == "pythonw.exe":
        candidate = executable.with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return str(executable)


class BackendEnv:
    """
    A virtual environment dedicated to one model backend.

    Args:
        key: Directory name of the environment, e.g. "demucs"
        python_versions: (major, minor) versions the backend supports, in
                         order of preference
        recipe: Version of the install recipe. Bump it when the packages a
                backend needs change, so stale environments get reinstalled.
    """

    def __init__(self, key: str, python_versions: Sequence[Tuple[int, int]] = ((3, 10), (3, 11)),
                 recipe: int = 1):
        self.key = key
        self.python_versions = tuple(python_versions)
        self.recipe = recipe

    @property
    def path(self) -> Path:
        return paths.envs_dir() / self.key

    @property
    def python(self) -> Path:
        if IS_WINDOWS:
            return self.path / "Scripts" / "python.exe"
        return self.path / "bin" / "python"

    @property
    def marker(self) -> Path:
        return self.path / MARKER_FILE

    def script(self, name: str) -> Path:
        """Path to a console script installed in the environment."""
        if IS_WINDOWS:
            return self.path / "Scripts" / f"{name}.exe"
        return self.path / "bin" / name

    def info(self) -> dict:
        """Contents of the install marker, or an empty dict if not installed."""
        try:
            with open(self.marker, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def is_installed(self) -> bool:
        """Whether the environment was installed completely with the current recipe."""
        return self.python.exists() and self.info().get("recipe") == self.recipe

    def exists(self) -> bool:
        return self.path.exists()

    def size(self) -> int:
        return paths.dir_size(self.path) if self.path.exists() else 0

    def subprocess_env(self, extra: Optional[dict] = None) -> dict:
        """Environment variables for running the backend's Python."""
        env = child_env(extra)
        env.pop("VIRTUAL_ENV", None)
        ffmpeg_dir = ffmpeg.ffmpeg_path_dir()
        if ffmpeg_dir:
            env["PATH"] = ffmpeg_dir + os.pathsep + env.get("PATH", "")
        return env

    def _venv_command(self) -> List[str]:
        """Find an interpreter of a supported version and build the venv command."""
        wanted = self.python_versions
        candidates: List[List[str]] = [[_base_python()]]
        for major, minor in wanted:
            if IS_WINDOWS and shutil.which("py"):
                candidates.append(["py", f"-{major}.{minor}"])
            named = shutil.which(f"python{major}.{minor}")
            if named:
                candidates.append([named])
        for command in candidates:
            if _interpreter_version(command) in wanted:
                return command + ["-m", "venv", str(self.path)]
        uv = shutil.which("uv")
        if uv:
            major, minor = wanted[0]
            return [uv, "venv", "--seed", "--python", f"{major}.{minor}", str(self.path)]
        versions = " or ".join(f"{major}.{minor}" for major, minor in wanted)
        raise EnvError(
            f"This model needs Python {versions}, but CaptainStems is running on Python "
            f"{sys.version_info[0]}.{sys.version_info[1]} and no compatible interpreter was found.\n"
            f"Install Python {wanted[0][0]}.{wanted[0][1]} from python.org and try again."
        )

    def create(self, log: LogCallback = None, cancel_event: Optional[threading.Event] = None) -> None:
        """Create a fresh, empty environment (replacing any existing one)."""
        self.remove()
        command = self._venv_command()
        _log(log, f"Creating environment: {self.path}")
        self._run(command, log, cancel_event, "create the Python environment")
        self.pip(["install", "--upgrade", "pip"], log, cancel_event)

    def pip(self, args: Sequence[str], log: LogCallback = None,
            cancel_event: Optional[threading.Event] = None) -> None:
        """Run pip inside the environment."""
        command = [str(self.python), "-m", "pip"] + list(args) + ["--disable-pip-version-check"]
        _log(log, "> pip " + " ".join(args))
        self._run(command, log, cancel_event, "install packages (pip " + " ".join(args[:2]) + ")")

    def run_python(self, args: Sequence[str], log: LogCallback = None,
                   cancel_event: Optional[threading.Event] = None, extra_env: Optional[dict] = None,
                   action: str = "run the model") -> None:
        """Run the environment's Python with the given arguments."""
        self._run([str(self.python)] + list(args), log, cancel_event, action, extra_env)

    def _run(self, command: Sequence[str], log: LogCallback, cancel_event: Optional[threading.Event],
             action: str, extra_env: Optional[dict] = None) -> None:
        returncode, tail = run_streaming(
            command,
            env=self.subprocess_env(extra_env),
            on_line=log,
            cancel_event=cancel_event,
        )
        if returncode != 0:
            details = "\n".join(tail[-12:]) if tail else "no output"
            raise EnvError(f"Failed to {action} (exit code {returncode}):\n{details}")

    def mark_installed(self, **details) -> None:
        """Record that installation finished successfully."""
        data = {
            "backend": self.key,
            "recipe": self.recipe,
            "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        data.update(details)
        with open(self.marker, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def remove(self) -> bool:
        """Delete the environment. Returns True if nothing is left of it."""
        return paths.remove_tree(self.path)


def _log(log: LogCallback, message: str) -> None:
    if log is not None:
        log(message)


__all__ = [
    "BackendEnv",
    "EnvError",
    "ProcessCancelled",
    "has_nvidia_gpu",
    "torch_install_args",
    "IS_WINDOWS",
    "IS_MACOS",
    "IS_APPLE_SILICON",
]
