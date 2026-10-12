#!/usr/bin/env python3
"""
CaptainStems - Unified Entrypoint Script

This script serves as the single entrypoint for CaptainStems, handling:
1. Dependency management for the application
2. Model installation (each model family gets its own environment)
3. Application launching
4. Separating files without the user interface

Usage:
  python captain.py                      # Run the application with dependency checks
  python captain.py --setup              # Setup/install dependencies only
  python captain.py --check              # Show what is installed
  python captain.py --list-models        # List the available models
  python captain.py --install-model X    # Install a model family (demucs, spleeter, bandsplit, d3net, all)
  python captain.py --uninstall-model X  # Remove a model family again
  python captain.py --separate song.mp3  # Separate files from the command line
"""

import os
import sys
import subprocess
import platform
import argparse
import importlib.util
from typing import List, Optional

VERSION = "1.0.0"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS_FILE = os.path.join(APP_DIR, "requirements.txt")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Import name -> package providing it, for the application's own dependencies
CORE_MODULES = {
    "PyQt6": "PyQt6",
    "numpy": "numpy",
    "soundfile": "soundfile",
    "imageio_ffmpeg": "imageio-ffmpeg",
}

# Names accepted by --install-model, mapped to backend keys
MODEL_ALIASES = {
    "demucs": "demucs",
    "demucs-v3": "demucs",
    "spleeter": "spleeter",
    "bandsplit": "bandsplit",
    "d3net": "d3net",
}

# Define colors for terminal output
class Colors:
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color

def setup_console() -> None:
    """Make colored, non-ASCII output work on every terminal."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if platform.system() == "Windows":
        # Enables ANSI escape sequences in the classic Windows console
        os.system("")
    if not sys.stdout.isatty():
        for name in ("GREEN", "YELLOW", "RED", "BLUE", "BOLD", "NC"):
            setattr(Colors, name, "")

def print_header(title: str) -> None:
    """Print a formatted header."""
    print(f"\n{Colors.BLUE}{Colors.BOLD}{'=' * 60}{Colors.NC}")
    print(f"{Colors.BLUE}{Colors.BOLD}{title}{Colors.NC}")
    print(f"{Colors.BLUE}{Colors.BOLD}{'=' * 60}{Colors.NC}")

def print_success(msg: str) -> None:
    """Print a success message."""
    print(f"{Colors.GREEN}✓ {msg}{Colors.NC}")

def print_warning(msg: str) -> None:
    """Print a warning message."""
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.NC}")

def print_error(msg: str) -> None:
    """Print an error message."""
    print(f"{Colors.RED}✗ {msg}{Colors.NC}")

def print_step(msg: str) -> None:
    """Print a step message."""
    print(f"{Colors.BOLD}→ {msg}{Colors.NC}")

# Check Python version
PYTHON_VERSION_STR = platform.python_version()
IS_RECOMMENDED_PYTHON = sys.version_info[:2] == (3, 10)

def check_python_compatibility() -> bool:
    """Check Python version compatibility and print appropriate messages."""
    if sys.version_info < (3, 9):
        print_error(f"Python {PYTHON_VERSION_STR} is too old. CaptainStems needs Python 3.9 or newer.")
        return False

    print_success(f"Python {PYTHON_VERSION_STR} detected")
    if not IS_RECOMMENDED_PYTHON:
        print_warning("Python 3.10 is recommended: every model supports it.")
        print_warning("Models that need another version look for a Python 3.10 installation (or uv) when installed.")
    return True

# Package management utilities
def missing_core_modules() -> List[str]:
    """
    Check which of the application's own dependencies are missing.

    Returns:
        List of package names that are not installed
    """
    return [package for module, package in CORE_MODULES.items()
            if importlib.util.find_spec(module) is None]

def install_core_dependencies() -> bool:
    """
    Install core dependencies from requirements.txt.

    Returns:
        True if all dependencies are installed
    """
    missing = missing_core_modules()
    if not missing:
        print_success("All core dependencies are installed")
        return True

    print_step(f"Installing missing core dependencies: {', '.join(missing)}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS_FILE])
    except (subprocess.CalledProcessError, OSError) as e:
        print_error(f"Failed to install core dependencies: {e}")
        print(f"  Try manually: {sys.executable} -m pip install -r requirements.txt")
        return False

    importlib.invalidate_caches()
    still_missing = missing_core_modules()
    if still_missing:
        print_error(f"Still missing after installation: {', '.join(still_missing)}")
        return False

    print_success("Core dependencies installed successfully")
    return True

def check_ffmpeg() -> bool:
    """
    Report which FFmpeg will be used.

    Returns:
        True if FFmpeg is available
    """
    from core import ffmpeg

    if ffmpeg.has_system_ffmpeg():
        print_success("FFmpeg is installed")
        return True
    if ffmpeg.find_ffmpeg():
        print_success("Using the FFmpeg bundled with imageio-ffmpeg")
        return True
    print_warning("FFmpeg not found. Install it with:")
    print(f"  {ffmpeg.install_hint()}")
    return False

# Model management
def resolve_backends(name: str) -> List[str]:
    """Translate a --install-model argument into backend keys."""
    from models import registry

    if name == "all":
        return list(registry.backend_models())
    return [MODEL_ALIASES[name]]

def install_model(name: str) -> bool:
    """
    Install a model family into its own environment.

    Args:
        name: demucs, spleeter, bandsplit, d3net or all

    Returns:
        True if installation was successful
    """
    from models import registry

    models = registry.backend_models()
    success = True
    for backend in resolve_backends(name):
        model = models[backend]
        title = registry.BACKEND_TITLES[backend]
        print_header(f"Installing {title}")
        print_step(f"Environment: {model.env.path}")
        print_step(f"Download size: {model.INSTALL_SIZE}")
        try:
            installed = model.install_dependencies(log=lambda line: print(f"  {line}"))
        except KeyboardInterrupt:
            model.env.remove()
            print_error("Installation cancelled")
            return False
        if installed:
            print_success(f"{title} installed successfully")
        else:
            print_error(f"Failed to install {title}")
            success = False
    return success

def uninstall_model(name: str) -> bool:
    """
    Remove a model family: its environment and downloaded weights.

    Returns:
        True if everything was removed
    """
    from models import registry

    models = registry.backend_models()
    success = True
    for backend in resolve_backends(name):
        title = registry.BACKEND_TITLES[backend]
        print_step(f"Removing {title}...")
        if models[backend].uninstall_dependencies():
            print_success(f"{title} removed")
        else:
            print_error(f"Could not remove all files of {title}")
            success = False
    return success

def list_models() -> None:
    """Print the available models and whether they are installed."""
    from models import registry

    installed = {backend: model.available for backend, model in registry.backend_models().items()}
    for family in registry.FAMILIES.values():
        state = "installed" if installed[family.backend] else "not installed"
        print(f"\n{Colors.BOLD}{family.title}{Colors.NC} ({state})")
        for model_name, description in family.models.items():
            identifier = registry.model_id(family.key, model_name)
            print(f"  {identifier:<24} {description}")

def check_status() -> int:
    """Print the state of the installation."""
    print_header("Checking Dependencies")
    check_python_compatibility()

    print_step("Checking core dependencies...")
    missing = missing_core_modules()
    if missing:
        print_warning(f"Missing {len(missing)} core dependencies")
        for package in missing:
            print(f"  - {package}")
        print(f"  Run: {os.path.basename(sys.executable)} captain.py --setup")
        return 1
    print_success("All core dependencies are installed")
    check_ffmpeg()

    from core import paths
    from core.envs import has_nvidia_gpu
    from models import registry

    print_success("NVIDIA GPU detected" if has_nvidia_gpu() else "No NVIDIA GPU detected (models run on the CPU)")

    print("\nModel status:")
    for backend, model in registry.backend_models().items():
        title = registry.BACKEND_TITLES[backend]
        if model.available:
            details = [model.env.info().get("package"), paths.format_size(model.installed_size())]
            print_success(f"{title} is installed ({', '.join(d for d in details if d)})")
        else:
            print_warning(f"{title} is not installed")
    print(f"\nModels are stored in: {paths.app_data_dir()}")
    return 0

def separate_files(args) -> int:
    """
    Separate audio files from the command line.

    Returns:
        Exit code
    """
    from core import paths, pipeline
    from core.settings import DEFAULTS
    from models import registry

    identifier = registry.find_model_id(args.model)
    if identifier is None:
        print_error(f"Unknown model: {args.model}")
        print("  Use --list-models to see the available models.")
        return 2
    model = registry.create_model(identifier)
    label = registry.display_name(identifier)
    if not model.available:
        print_error(f"{label} is not installed.")
        print(f"  Install it with: python captain.py --install-model {model.BACKEND}")
        return 1
    if args.two_stems and not model.supports_two_stems:
        print_warning(f"{label} does not support two-stems mode. Ignoring --two-stems.")
        args.two_stems = False

    options = {
        "device": args.device,
        "demucs_shifts": DEFAULTS["demucs_shifts"],
        "demucs_overlap": DEFAULTS["demucs_overlap"],
        "spleeter_mwf": DEFAULTS["spleeter_mwf"],
    }

    print_header(f"Separating with {label}")
    session_dir = paths.new_session_dir()
    folders = pipeline.ExportFolders()
    failures = 0
    try:
        for source in args.separate:
            print_step(os.path.basename(source))
            last = {"status": "", "percent": -1}

            def show(percent=None, status=None):
                if status is not None:
                    last["status"] = status
                if percent is not None:
                    last["percent"] = percent
                if sys.stdout.isatty():
                    print(f"\r  {last['status']:<40} {max(0, last['percent']):3d}%", end="", flush=True)
                elif status is not None:
                    print(f"  {status}", flush=True)

            try:
                result = pipeline.separate_file(
                    model, source, session_dir,
                    two_stems=args.two_stems,
                    options=options,
                    progress=lambda value: show(percent=value),
                    status=lambda text: show(status=text),
                    model_label=label,
                )
                destination = args.output or os.path.dirname(os.path.abspath(source))
                folder = pipeline.export_result(result, destination, args.format, args.bitrate,
                                                folders=folders)
                result.discard()
            except KeyboardInterrupt:
                print()
                print_error("Cancelled")
                return 130
            except Exception as e:
                if sys.stdout.isatty():
                    print()
                print_error(f"Failed: {e}")
                failures += 1
                continue
            if sys.stdout.isatty():
                print()
            print_success(f"Stems saved to {folder}")
    finally:
        paths.remove_tree(session_dir)
    return 1 if failures else 0

def run_application() -> int:
    """
    Run the main application.

    Returns:
        Exit code from the application
    """
    print_header("Starting CaptainStems")

    try:
        # Run the main application
        return subprocess.call([sys.executable, os.path.join(APP_DIR, "main.py")])
    except Exception as e:
        print_error(f"Error running application: {e}")
        return 1

def setup_environment() -> bool:
    """
    Set up the environment with core dependencies.

    Returns:
        True if setup was successful
    """
    print_header("Setting Up CaptainStems Environment")

    # Check Python compatibility
    if not check_python_compatibility():
        return False

    # Check/install core dependencies
    if not install_core_dependencies():
        print_error("Failed to install core dependencies")
        return False

    # Check for FFmpeg
    if not check_ffmpeg():
        print_warning("Audio files cannot be read without FFmpeg")

    print_success("Environment setup complete")
    return True

def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point.

    Returns:
        Exit code
    """
    setup_console()

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="CaptainStems - Audio Source Separation Tool")
    parser.add_argument("--setup", action="store_true", help="Set up environment only")
    parser.add_argument("--install-model", choices=sorted(MODEL_ALIASES) + ["all"],
                      help="Install a model family into its own environment")
    parser.add_argument("--uninstall-model", choices=sorted(MODEL_ALIASES) + ["all"],
                      help="Remove a model family and its downloaded weights")
    parser.add_argument("--check", action="store_true", help="Check dependency status only")
    parser.add_argument("--list-models", action="store_true", help="List the available models")
    parser.add_argument("--version", action="store_true", help="Show version information")

    separation = parser.add_argument_group("separating files without the user interface")
    separation.add_argument("--separate", nargs="+", metavar="FILE", help="Audio files to separate")
    separation.add_argument("--model", default="demucs4:htdemucs",
                          help="Model to use, see --list-models (default: demucs4:htdemucs)")
    separation.add_argument("--two-stems", action="store_true",
                          help="Separate into vocals and instrumental only (Demucs)")
    separation.add_argument("--output", metavar="DIR",
                          help="Folder for the stems (default: next to each file)")
    separation.add_argument("--format", default="wav", choices=["wav", "flac", "aiff", "mp3", "m4a", "ogg"],
                          help="Audio format of the stems (default: wav)")
    separation.add_argument("--bitrate", default="320k", choices=["128k", "192k", "256k", "320k"],
                          help="Bitrate for mp3, m4a and ogg (default: 320k)")
    separation.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"],
                          help="Device to run the model on (default: auto)")

    args = parser.parse_args(argv)

    # Show version information
    if args.version:
        print("CaptainStems - Audio Source Separation Tool")
        print(f"Version: {VERSION}")
        print(f"Python: {PYTHON_VERSION_STR}")
        print(f"Platform: {platform.system()} {platform.machine()}")
        return 0

    # Check dependencies only
    if args.check:
        return check_status()

    # Setup only
    if args.setup:
        return 0 if setup_environment() else 1

    # Everything below needs the core dependencies
    if not install_core_dependencies():
        return 1

    if args.list_models:
        list_models()
        return 0

    # Install or remove a model family
    if args.uninstall_model:
        return 0 if uninstall_model(args.uninstall_model) else 1

    if args.install_model:
        return 0 if install_model(args.install_model) else 1

    if args.separate:
        return separate_files(args)

    # Run application (default)
    check_python_compatibility()
    check_ffmpeg()
    return run_application()

if __name__ == "__main__":
    sys.exit(main())
