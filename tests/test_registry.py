import hashlib
import json

import pytest
from conftest import add_fake_model
from typer.testing import CliRunner

from captainstems import registry as registry_module
from captainstems.cli import app
from captainstems.registry import Manifest, Registry, RegistryError

runner = CliRunner()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_empty_registry(home):
    registry = Registry()
    assert registry.list() == [] and registry.root == home / "models"
    with pytest.raises(RegistryError, match="is not installed"):
        registry.get("nothing")


def test_add_writes_a_manifest_and_fills_in_hashes(home, tmp_path):
    weights = tmp_path / "my-model.ckpt"
    weights.write_bytes(b"weights")
    config = tmp_path / "my-config.yaml"
    config.write_text("training: {}\n")
    manifest = Manifest(
        id="custom",
        backend="msst",
        arch="bs_roformer",
        config="my-config.yaml",
        weights="my-model.ckpt",
        stems=["vocals"],
    )
    model = Registry().add(manifest, {"my-model.ckpt": weights, "my-config.yaml": config})

    assert weights.exists(), "files are copied unless --move is given"
    stored = json.loads((model.folder / "manifest.json").read_text())
    assert stored["sha256"]["my-model.ckpt"] == sha(b"weights")
    assert Registry().get("custom").manifest.stems == ["vocals"]
    with pytest.raises(RegistryError, match="already exists"):
        Registry().add(manifest, {"my-model.ckpt": weights, "my-config.yaml": config})


def test_add_needs_every_file(home, tmp_path):
    manifest = Manifest(id="partial", backend="msst", arch="x", config="c.yaml", weights="w.ckpt", stems=["a"])
    with pytest.raises(RegistryError, match="missing c.yaml, w.ckpt"):
        Registry().add(manifest)


def test_manifest_validation(home):
    base = dict(id="ok", backend="msst", weights="w.ckpt", stems=["a"])
    Manifest(**base)
    for change, match in [
        ({"id": "has space"}, "may only contain"),
        ({"id": "../escape"}, "may only contain"),
        ({"backend": "tensorflow"}, "backend"),
        ({"stems": []}, "stems"),
        ({"surprise": 1}, "surprise"),
    ]:
        with pytest.raises(ValueError, match=match):
            Manifest(**{**base, **change})


def test_verification_catches_changed_weights(home, fake_backend):
    registry = Registry()
    model = add_fake_model(registry, "checked", ["vocals"])
    first = model.sha256()
    assert model.verify()["model.ckpt"] == sha(b"weights of checked")

    (model.folder / "model.ckpt").write_bytes(b"something else entirely")
    with pytest.raises(RegistryError, match="does not match its manifest"):
        Registry().get("checked").verify()
    assert first != sha(b"something else entirely")


def test_hashes_are_remembered_until_a_file_changes(home, fake_backend, monkeypatch):
    model = add_fake_model(Registry(), "cached", ["vocals"])
    calls = []
    real = registry_module.audio.file_sha256
    monkeypatch.setattr(registry_module.audio, "file_sha256", lambda path: calls.append(path) or real(path))
    model.hashes()
    model.hashes()
    assert calls == [], "hashing was done when the model was added"
    (model.folder / ".verified.json").unlink()
    model.hashes()
    assert len(calls) == 2


def test_broken_manifests_are_reported_not_fatal(home, fake_backend):
    registry = Registry()
    add_fake_model(registry, "good", ["vocals"])
    bad = registry.root / "bad"
    bad.mkdir()
    (bad / "manifest.json").write_text("{not json")
    renamed = registry.root / "renamed"
    renamed.mkdir()
    (renamed / "manifest.json").write_text((registry.root / "good" / "manifest.json").read_text())

    registry.scan()
    assert [model.id for model in registry.list()] == ["good"]
    assert set(registry.problems) == {"bad", "renamed"}
    with pytest.raises(RegistryError, match="broken manifest"):
        registry.get("bad")


def test_remove(home, fake_backend):
    registry = Registry()
    add_fake_model(registry, "gone", ["vocals"])
    registry.remove("gone")
    assert not (registry.root / "gone").exists() and not registry.has("gone")
    for bad in ("gone", "..", "../x"):
        with pytest.raises(RegistryError):
            registry.remove(bad)


@pytest.fixture
def curated(tmp_path, monkeypatch):
    """A curated catalog whose files are served from disk."""
    source = tmp_path / "server"
    source.mkdir()
    (source / "config.yaml").write_bytes(b"training: {}\n")
    (source / "model.ckpt").write_bytes(b"curated weights")
    entry = {
        "id": "curated-model",
        "name": "Curated",
        "backend": "msst",
        "arch": "bs_roformer",
        "config": "config.yaml",
        "weights": "model.ckpt",
        "stems": ["vocals"],
        "sample_rate": 44100,
        "license": "test",
        "files": [
            {
                "name": "config.yaml",
                "url": (source / "config.yaml").as_uri(),
                "sha256": sha(b"training: {}\n"),
                "size": 13,
            },
            {
                "name": "model.ckpt",
                "url": (source / "model.ckpt").as_uri(),
                "sha256": sha(b"curated weights"),
                "size": 15,
            },
        ],
    }
    monkeypatch.setattr(registry_module, "load_curated", lambda: {"curated-model": entry})
    return entry


def test_manifest_can_name_stems_differently_from_the_config():
    # A model's config may call its outputs "Instrumental" or "other"; recipes use the manifest's names
    manifest = Manifest(
        id="deux",
        backend="msst",
        arch="mel_band_roformer",
        config="c.yaml",
        weights="w.ckpt",
        stems=["vocals", "instrumental"],
        config_stems=["Vocals", "Instrumental"],
    )
    assert manifest.config_stems == ["Vocals", "Instrumental"]
    assert (
        Manifest(id="plain", backend="msst", arch="x", config="c.yaml", weights="w.ckpt", stems=["a"]).config_stems
        is None
    )


def test_fetch_downloads_verifies_and_installs(home, curated):
    seen = []
    model = Registry().fetch("curated-model", progress=lambda name, done, total: seen.append(name))
    assert model.missing_files() == [] and set(seen) == {"config.yaml", "model.ckpt"}
    assert model.manifest.sha256 == {"config.yaml": sha(b"training: {}\n"), "model.ckpt": sha(b"curated weights")}
    assert model.manifest.source["model.ckpt"].startswith("file:")
    model.verify()

    seen.clear()
    Registry().fetch("curated-model", progress=lambda name, done, total: seen.append(name))
    assert seen == [], "files that are already correct are not downloaded again"


def test_fetch_rejects_a_wrong_checksum(home, curated):
    curated["files"][1]["sha256"] = "0" * 64
    with pytest.raises(RegistryError, match="Checksum mismatch"):
        Registry().fetch("curated-model")
    folder = home / "models" / "curated-model"
    assert not (folder / "model.ckpt").exists() and not (folder / "model.ckpt.part").exists()
    assert not Registry().has("curated-model")
    with pytest.raises(RegistryError, match="not a curated model"):
        Registry().fetch("unknown")


def test_catalog_lists_installed_and_fetchable(home, curated, fake_backend):
    registry = Registry()
    add_fake_model(registry, "mine", ["vocals"])
    rows = {row["id"]: row for row in registry.catalog()}
    assert rows["mine"]["installed"] is True
    assert rows["curated-model"]["installed"] is False and rows["curated-model"]["download_bytes"] == 28
    assert "files" not in rows["curated-model"]


def test_catalog_adds_published_scores_to_installed_models(home, curated, fake_backend):
    # A manifest written at fetch time may predate the scores; the catalog fills them in
    curated["scores"] = {"vocals": 11.2}
    curated["benchmark"] = "a test set"
    Registry().fetch("curated-model")
    folder = home / "models" / "curated-model"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("scores", None)
    manifest.pop("benchmark", None)
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    row = {entry["id"]: entry for entry in Registry().catalog()}["curated-model"]
    assert (
        row["installed"] and row["curated"] and row["scores"] == {"vocals": 11.2} and row["benchmark"] == "a test set"
    )


def test_shipped_curated_catalog_is_well_formed():
    entries = registry_module.load_curated()
    assert {"htdemucs", "htdemucs_6s", "mel-band-roformer-vocals-kim", "scnet-large", "dereverb-mel-roformer"} <= set(
        entries
    )
    for model_id, entry in entries.items():
        files = {item["name"] for item in entry["files"]}
        fields = {key: value for key, value in entry.items() if key != "files"}
        manifest = Manifest(**fields)
        assert manifest.id == model_id
        assert set(manifest.files) == files, model_id
        for item in entry["files"]:
            assert item["url"].startswith("https://") and len(item["sha256"]) == 64 and item["size"] > 0
        assert entry["license"], f"{model_id} must state its license"
        if manifest.scores:
            assert manifest.benchmark, f"{model_id}: scores need the benchmark they were measured on"
            assert all(0 < value < 60 for value in manifest.scores.values()), model_id
    scored = [model_id for model_id, entry in entries.items() if entry.get("scores")]
    assert {"mel-band-roformer-deux", "scnet-xl-ihf", "htdemucs"} <= set(scored)


# CLI ------------------------------------------------------------------------------


def test_cli_models_add_list_verify_remove(home, tmp_path):
    weights = tmp_path / "w.ckpt"
    weights.write_bytes(b"abc")
    config = tmp_path / "c.yaml"
    config.write_text("x: 1\n")
    result = runner.invoke(
        app,
        ["models", "add", "cli-model", "-b", "msst", "-a", "mdx23c", "-w", str(weights), "-c", str(config)]
        + ["-s", "vocals, other", "-d", "overlap=4", "-d", "normalize=true", "--license", "CC0"],
    )
    assert result.exit_code == 0, result.output
    manifest = Registry().get("cli-model").manifest
    assert manifest.stems == ["vocals", "other"] and manifest.defaults == {"overlap": 4, "normalize": True}
    assert manifest.license == "CC0"

    listed = json.loads(runner.invoke(app, ["models", "list", "--json"]).output)
    assert any(row["id"] == "cli-model" and row["installed"] for row in listed)
    assert runner.invoke(app, ["models", "verify"]).exit_code == 0
    assert runner.invoke(app, ["models", "add", "x y", "-b", "msst", "-w", str(weights), "-s", "a"]).exit_code == 2
    assert runner.invoke(app, ["models", "remove", "cli-model", "--yes"]).exit_code == 0
    assert not Registry().has("cli-model")
    assert runner.invoke(app, ["models", "remove", "cli-model", "--yes"]).exit_code == 1
