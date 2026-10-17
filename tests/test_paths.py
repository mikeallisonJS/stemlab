"""The per-user home folder, and its one-time adoption of the pre-release `~/.captainstems`."""

from pathlib import Path

from stemlab import paths


def test_home_adopts_legacy_folder(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("STEMLAB_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    legacy = tmp_path / ".captainstems"
    (legacy / "models" / "htdemucs").mkdir(parents=True)
    (legacy / "models" / "htdemucs" / "manifest.json").write_text("{}")

    home = paths.home()

    assert home == tmp_path / ".stemlab"
    assert (home / "models" / "htdemucs" / "manifest.json").exists()
    assert not legacy.exists()


def test_home_keeps_existing_folder(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("STEMLAB_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".stemlab").mkdir()
    (tmp_path / ".captainstems").mkdir()

    assert paths.home() == tmp_path / ".stemlab"
    assert (tmp_path / ".captainstems").exists()


def test_home_override_never_migrates(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".captainstems").mkdir()
    monkeypatch.setenv("STEMLAB_HOME", str(tmp_path / "elsewhere"))

    assert paths.home() == tmp_path / "elsewhere"
    assert (tmp_path / ".captainstems").exists()


def test_home_says_so_when_the_legacy_folder_cannot_move(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.delenv("STEMLAB_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".captainstems" / "models").mkdir(parents=True)

    def refuse(self, target):
        raise OSError("cross-device link")

    monkeypatch.setattr(Path, "rename", refuse)

    assert paths.home() == tmp_path / ".stemlab"
    assert (tmp_path / ".captainstems" / "models").exists()
    assert "could not move" in capsys.readouterr().err
