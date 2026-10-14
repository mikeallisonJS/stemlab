"""Filesystem locations used by CaptainStems."""

import getpass
import os
import shutil
import sys
import tempfile
from pathlib import Path

APP_NAME = "CaptainStems"

# Session directories are named <prefix><process id>_<random>
SESSION_PREFIX = "session_"


def app_data_dir() -> Path:
    """
    Directory holding everything the application installs or downloads
    (model environments and model weights). Override with CAPTAINSTEMS_HOME.
    """
    override = os.environ.get("CAPTAINSTEMS_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = (Path(local) if local else Path.home() / "AppData" / "Local") / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".local" / "share") / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def envs_dir() -> Path:
    """Directory containing one isolated Python environment per model backend."""
    path = app_data_dir() / "envs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def weights_dir(backend: str, create: bool = False) -> Path:
    """Directory where a backend keeps its downloaded model weights."""
    path = app_data_dir() / "weights" / backend
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def bin_dir() -> Path:
    """Directory for helper binaries managed by the application."""
    path = app_data_dir() / "bin"
    path.mkdir(parents=True, exist_ok=True)
    return path


def temp_root() -> Path:
    """Root for temporary session directories (one per user on shared machines)."""
    try:
        user = getpass.getuser()
    except Exception:
        user = str(os.getuid()) if hasattr(os, "getuid") else "user"
    path = Path(tempfile.gettempdir()) / f"captainstems-{safe_name(user)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_session_dir() -> Path:
    """Create a temporary directory for the separation results of this run."""
    return Path(tempfile.mkdtemp(prefix=f"{SESSION_PREFIX}{os.getpid()}_", dir=temp_root()))


def process_alive(pid: int) -> bool:
    """Whether a process with the given id is currently running."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            # Access denied means the process exists but belongs to someone else
            return ctypes.get_last_error() == 5
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def remove_tree(path) -> bool:
    """Delete a directory tree, returning False if something could not be removed."""
    path = Path(path)
    if not path.exists():
        return True
    shutil.rmtree(path, ignore_errors=True)
    return not path.exists()


def clean_stale_sessions() -> int:
    """
    Remove session directories left behind by previous runs that crashed.
    A session is stale once the process that created it is gone.
    """
    removed = 0
    for entry in temp_root().glob(f"{SESSION_PREFIX}*"):
        try:
            owner = int(entry.name[len(SESSION_PREFIX):].split("_", 1)[0])
        except ValueError:
            continue
        if owner != os.getpid() and not process_alive(owner) and remove_tree(entry):
            removed += 1
    return removed


def dir_size(path) -> int:
    """Total size in bytes of all files below a directory."""
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def format_size(num_bytes: int) -> str:
    """Human readable file size."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def safe_name(name: str) -> str:
    """Make a string safe to use as a file or directory name on every platform."""
    cleaned = "".join("_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in name)
    cleaned = cleaned.strip().rstrip(". ")
    return cleaned or "audio"
