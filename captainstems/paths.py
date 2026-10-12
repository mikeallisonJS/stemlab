"""Filesystem locations used by the engine."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MSST_DIR = REPO_ROOT / "third_party" / "msst"


def home() -> Path:
    """Root for everything CaptainStems stores per user. Override with CAPTAINSTEMS_HOME."""
    override = os.environ.get("CAPTAINSTEMS_HOME")
    root = Path(override) if override else Path.home() / ".captainstems"
    root.mkdir(parents=True, exist_ok=True)
    return root


def models_dir() -> Path:
    """Registry root: one subfolder per model."""
    path = home() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    """Intermediate stems, keyed by what produced them."""
    path = home() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def uploads_dir() -> Path:
    """Files dropped onto the UI: a browser can only hand over their bytes, not their location."""
    path = home() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def outputs_dir() -> Path:
    """Where the stems of dropped files go when no output folder was chosen."""
    path = home() / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_file() -> Path:
    """Per-user settings such as the chosen torch flavor."""
    return home() / "config.json"
