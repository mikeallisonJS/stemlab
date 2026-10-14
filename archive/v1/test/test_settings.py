from PyQt6.QtCore import QSettings

import pytest

from core.settings import DEFAULTS, Settings


def reopen(tmp_path):
    """Settings read back from disk, where every value is stored as text."""
    return Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))


def test_defaults(settings):
    for key, default in DEFAULTS.items():
        assert settings.get(key) == default
    assert settings.export_format() == "wav"
    assert settings.theme() == "system"


def test_values_keep_their_type_after_reload(settings, tmp_path):
    settings.set("auto_save", True)
    settings.set("open_results", False)
    settings.set("demucs_shifts", 4)
    settings.set("demucs_overlap", 0.5)
    settings.set("output_dir", "C:/Music/Stems")
    settings.set("custom_models", ["demucs4:htdemucs_ft", "spleeter:4stems"])
    settings.sync()

    loaded = reopen(tmp_path)
    assert loaded.get("auto_save") is True
    assert loaded.get("open_results") is False
    assert loaded.get("demucs_shifts") == 4
    assert loaded.get("demucs_overlap") == 0.5
    assert loaded.get("output_dir") == "C:/Music/Stems"
    assert loaded.custom_models() == ["demucs4:htdemucs_ft", "spleeter:4stems"]


def test_invalid_stored_values_fall_back(settings, tmp_path):
    raw = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    raw.setValue("demucs_shifts", "many")
    raw.setValue("export_format", "wma")
    raw.setValue("export_bitrate", "9000k")
    raw.setValue("theme", "neon")
    raw.setValue("custom_models", "{broken json")
    raw.setValue("device", "quantum")
    raw.sync()

    loaded = reopen(tmp_path)
    assert loaded.get("demucs_shifts") == DEFAULTS["demucs_shifts"]
    assert loaded.export_format() == "wav"
    assert loaded.export_bitrate() == "320k"
    assert loaded.theme() == "system"
    assert loaded.custom_models() == []
    assert loaded.processing_options()["device"] == "auto"


def test_processing_options_are_clamped(settings):
    settings.set("demucs_shifts", 500)
    settings.set("demucs_overlap", 5.0)
    options = settings.processing_options()
    assert options["demucs_shifts"] == 10
    assert options["demucs_overlap"] == 0.9
    assert set(options) == {"device", "demucs_shifts", "demucs_overlap", "spleeter_mwf"}


def test_unknown_keys_are_rejected(settings):
    with pytest.raises(KeyError):
        settings.set("no_such_setting", 1)


def test_list_defaults_are_not_shared(settings):
    settings.get("custom_models").append("demucs4:htdemucs")
    assert settings.get("custom_models") == []
