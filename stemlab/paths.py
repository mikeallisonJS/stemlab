"""Filesystem locations used by the engine."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The repository, where the recipes, the MSST submodule and the built UI live.
# The packaged app installs the engine as a wheel and ships those as resources:
# it points STEMLAB_ROOT at a folder laid out the same way.
REPO_ROOT = (
    Path(os.environ["STEMLAB_ROOT"])
    if os.environ.get("STEMLAB_ROOT")
    else Path(__file__).resolve().parent.parent
)
MSST_DIR = REPO_ROOT / "third_party" / "msst"


def home() -> Path:
    """Root for everything Stemlab stores per user. Override with STEMLAB_HOME."""
    override = os.environ.get("STEMLAB_HOME")
    root = Path(override) if override else Path.home() / ".stemlab"
    if not override and not root.exists():
        _adopt_legacy_home(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _adopt_legacy_home(root: Path) -> None:
    """Stemlab was CaptainStems before its first release: take over `~/.captainstems`
    (downloaded models, cache, outputs) by renaming it, once, instead of fetching everything again."""
    legacy = root.parent / ".captainstems"
    if not legacy.is_dir():
        return
    try:
        legacy.rename(root)
    except OSError as error:
        # Another drive or no permission: start fresh, the old folder stays. Said once, since
        # the new folder exists from here on and the rename is never tried again.
        print(
            f"stemlab: could not move {legacy} to {root} ({error}); starting with an empty "
            f"{root}. Move the models across yourself to keep them.",
            file=sys.stderr,
        )


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
