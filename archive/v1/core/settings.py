"""Persistent user preferences."""

import json
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QSettings

from core import ffmpeg

THEMES = ["system", "dark", "light"]
DEVICES = ["auto", "cpu", "cuda", "mps"]

DEFAULTS: Dict[str, Any] = {
    # Appearance
    "theme": "system",
    # Export
    "export_format": ffmpeg.DEFAULT_EXPORT_FORMAT,
    "export_bitrate": ffmpeg.DEFAULT_BITRATE,
    "auto_save": False,
    "output_dir": "",
    "open_results": True,
    # Processing
    "device": "auto",
    "demucs_shifts": 1,
    "demucs_overlap": 0.25,
    "spleeter_mwf": False,
    # Remembered state
    "last_model": "",
    "custom_models": [],
    "two_stems": False,
    "last_open_dir": "",
    "last_save_dir": "",
}


class Settings:
    """Typed access to the stored preferences, falling back to DEFAULTS."""

    def __init__(self, qsettings: Optional[QSettings] = None):
        self._settings = qsettings if qsettings is not None else QSettings("CaptainStems", "CaptainStems")

    def get(self, key: str) -> Any:
        default = DEFAULTS[key]
        raw = self._settings.value(key)
        if raw is None:
            return list(default) if isinstance(default, list) else default
        try:
            if isinstance(default, bool):
                if isinstance(raw, str):
                    return raw.strip().lower() in ("1", "true", "yes", "on")
                return bool(raw)
            if isinstance(default, int):
                return int(raw)
            if isinstance(default, float):
                return float(raw)
            if isinstance(default, list):
                value = json.loads(raw) if isinstance(raw, str) else list(raw)
                return value if isinstance(value, list) else list(default)
            return str(raw)
        except (TypeError, ValueError):
            return list(default) if isinstance(default, list) else default

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        if isinstance(DEFAULTS[key], list):
            value = json.dumps(list(value))
        self._settings.setValue(key, value)

    def sync(self) -> None:
        self._settings.sync()

    # Convenience accessors -------------------------------------------------

    def theme(self) -> str:
        theme = self.get("theme")
        return theme if theme in THEMES else DEFAULTS["theme"]

    def export_format(self) -> str:
        fmt = self.get("export_format")
        return fmt if fmt in ffmpeg.EXPORT_FORMATS else ffmpeg.DEFAULT_EXPORT_FORMAT

    def export_bitrate(self) -> str:
        bitrate = self.get("export_bitrate")
        return bitrate if bitrate in ffmpeg.BITRATES else ffmpeg.DEFAULT_BITRATE

    def custom_models(self) -> List[str]:
        return [str(item) for item in self.get("custom_models")]

    def processing_options(self) -> Dict[str, Any]:
        """Options handed to the separation models."""
        device = self.get("device")
        return {
            "device": device if device in DEVICES else "auto",
            "demucs_shifts": min(10, max(1, self.get("demucs_shifts"))),
            "demucs_overlap": min(0.9, max(0.05, self.get("demucs_overlap"))),
            "spleeter_mwf": self.get("spleeter_mwf"),
        }
