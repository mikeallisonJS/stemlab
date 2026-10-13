"""
The model registry: one folder per model below `~/.captainstems/models/`,
each holding a `manifest.json`, the model's config and its weights.

The folder name is the id used in recipes. Custom models are added by
dropping files in a folder and writing the manifest (`models add` does that).
`curated.json`, shipped with the package, lists known-good models by URL and
SHA-256 so `models fetch <id>` works out of the box. Weights are downloaded,
never bundled.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from captainstems import audio, paths

MANIFEST = "manifest.json"
VERIFIED = ".verified.json"
CURATED = Path(__file__).with_name("curated.json")

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")


class RegistryError(Exception):
    """A model is missing, malformed or failed verification."""


class Manifest(BaseModel):
    """Contents of a model's manifest.json."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = ""
    backend: Literal["msst", "demucs", "onnx"]
    #: Passed straight to the backend. For MSST it is the --model_type value.
    arch: str = ""
    config: str | None = None
    #: One file, or the set of files that make up a Demucs bag
    weights: str | list[str]
    #: SHA-256 of the weights file, or file name -> SHA-256 when there are several
    sha256: str | dict[str, str] | None = None
    #: The model's native output order
    stems: list[str] = Field(min_length=1)
    #: What the model's own config calls those outputs, when the manifest names them
    #: differently (e.g. "Instrumental" -> instrumental, "other" -> instrumental)
    config_stems: list[str] | None = None
    sample_rate: int = 44100
    #: Seed the knobs of nodes using this model
    defaults: dict[str, Any] = Field(default_factory=dict)
    #: Where the files came from; informational, and used by `models fetch`
    source: str | list[str] | dict[str, str] | None = None
    license: str = ""
    notes: str = ""
    #: Published SDR in dB per stem ("all" for a 4 stem average), and where it was measured.
    #: Benchmarks differ (MUSDB18, MVSEP multisong, a publisher's own set): compare within one only
    scores: dict[str, float] = Field(default_factory=dict)
    benchmark: str = ""
    #: MDX-Net models carry no config: dim_f, dim_t, n_fft, compensate
    onnx_params: dict[str, Any] | None = None
    #: Allow loading checkpoints that need Python's pickle (it can run code)
    unsafe_pickle: bool = False

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not ID_PATTERN.match(value):
            raise ValueError("model ids may only contain letters, digits, '.', '_' and '-'")
        return value

    @property
    def weight_files(self) -> list[str]:
        return [self.weights] if isinstance(self.weights, str) else list(self.weights)

    @property
    def files(self) -> list[str]:
        """Every file the model needs, config first."""
        return ([self.config] if self.config else []) + self.weight_files

    def expected_hashes(self) -> dict[str, str]:
        if self.sha256 is None:
            return {}
        if isinstance(self.sha256, str):
            return {self.weight_files[0]: self.sha256.lower()}
        return {name: digest.lower() for name, digest in self.sha256.items()}


class Model:
    """A model installed in the registry."""

    def __init__(self, folder: Path, manifest: Manifest):
        self.folder = folder
        self.manifest = manifest

    @property
    def id(self) -> str:
        return self.manifest.id

    def path(self, name: str) -> Path:
        return self.folder / name

    @property
    def config_path(self) -> Path | None:
        return self.path(self.manifest.config) if self.manifest.config else None

    @property
    def weight_paths(self) -> list[Path]:
        return [self.path(name) for name in self.manifest.weight_files]

    def missing_files(self) -> list[str]:
        return [name for name in self.manifest.files if not self.path(name).is_file()]

    def _fingerprint(self) -> dict:
        """Size and modification time of every file, to notice changes cheaply."""
        result = {}
        for name in self.manifest.files:
            stat = self.path(name).stat()
            result[name] = [stat.st_size, int(stat.st_mtime)]
        return result

    def hashes(self) -> dict[str, str]:
        """
        SHA-256 of every file. Hashing gigabytes takes a while, so results are
        remembered until a file's size or modification time changes.
        """
        missing = self.missing_files()
        if missing:
            raise RegistryError(f"Model '{self.id}' is incomplete: missing {', '.join(missing)}")
        record_path = self.folder / VERIFIED
        fingerprint = self._fingerprint()
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("fingerprint") == fingerprint:
                return record["hashes"]
        except (OSError, ValueError, KeyError):
            pass
        hashes = {name: audio.file_sha256(self.path(name)) for name in self.manifest.files}
        try:
            record_path.write_text(
                json.dumps({"fingerprint": fingerprint, "hashes": hashes}, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
        return hashes

    def verify(self) -> dict[str, str]:
        """
        Check the files against the hashes in the manifest (on first load, and
        again whenever a file changes).

        Returns:
            File name -> SHA-256 for every file of the model
        """
        hashes = self.hashes()
        for name, expected in self.manifest.expected_hashes().items():
            actual = hashes.get(name)
            if actual != expected:
                raise RegistryError(
                    f"Model '{self.id}': {name} does not match its manifest.\n"
                    f"  expected sha256 {expected}\n  found    sha256 {actual}"
                )
        return hashes

    def sha256(self) -> str:
        """One hash identifying the model: its weights file, or all of its files combined."""
        hashes = self.verify()
        weights = self.manifest.weight_files
        if len(weights) == 1 and not self.manifest.config:
            return hashes[weights[0]]
        digest = hashlib.sha256()
        for name in sorted(hashes):
            digest.update(f"{name}:{hashes[name]}\n".encode())
        return digest.hexdigest()

    def summary(self) -> dict:
        data = self.manifest.model_dump(exclude_none=True)
        data["installed"] = not self.missing_files()
        data["folder"] = str(self.folder)
        return data


def load_curated() -> dict[str, dict]:
    """Known-good models: id -> entry with the manifest fields plus download URLs."""
    with open(CURATED, encoding="utf-8") as f:
        entries = json.load(f)["models"]
    return {entry["id"]: entry for entry in entries}


def _download(
    url: str, target: Path, expected_sha256: str | None, progress: Callable[[int, int | None], None] | None
) -> str:
    """Download to `target` through a .part file, verifying the checksum before it is kept."""
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "captainstems"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, open(partial, "wb") as f:
            total = int(response.headers.get("Content-Length") or 0) or None
            done = 0
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    actual = digest.hexdigest()
    if expected_sha256 and actual != expected_sha256.lower():
        partial.unlink(missing_ok=True)
        raise RegistryError(f"Checksum mismatch for {url}\n  expected {expected_sha256}\n  got      {actual}")
    os.replace(partial, target)
    return actual


class Registry:
    """The models installed on this machine."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else paths.models_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self._models: dict[str, Model] = {}
        self.problems: dict[str, str] = {}
        self.scan()

    def scan(self) -> None:
        """Read every manifest below the root. Broken ones are reported, not fatal."""
        self._models.clear()
        self.problems.clear()
        for folder in sorted(self.root.iterdir()):
            manifest_path = folder / MANIFEST
            if not manifest_path.is_file():
                continue
            try:
                manifest = Manifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
                if manifest.id != folder.name:
                    raise ValueError(f"id '{manifest.id}' does not match its folder name")
            except Exception as e:
                self.problems[folder.name] = str(e)
                continue
            self._models[manifest.id] = Model(folder, manifest)

    def list(self) -> list[Model]:
        return list(self._models.values())

    def has(self, model_id: str) -> bool:
        return model_id in self._models

    def get(self, model_id: str) -> Model:
        if model_id in self._models:
            return self._models[model_id]
        if model_id in self.problems:
            raise RegistryError(f"Model '{model_id}' has a broken manifest: {self.problems[model_id]}")
        hint = ""
        if model_id in load_curated():
            hint = f" It is a curated model: run `captainstems models fetch {model_id}`."
        raise RegistryError(f"Model '{model_id}' is not installed.{hint}")

    def fetch(
        self, model_id: str, progress: Callable[[str, int, int | None], None] | None = None, force: bool = False
    ) -> Model:
        """Download a curated model, verify every file and write its manifest."""
        curated = load_curated()
        if model_id not in curated:
            raise RegistryError(f"'{model_id}' is not a curated model. Known: {', '.join(sorted(curated))}")
        entry = dict(curated[model_id])
        files = entry.pop("files")
        folder = self.root / model_id
        folder.mkdir(parents=True, exist_ok=True)

        for item in files:
            target = folder / item["name"]
            if target.is_file() and not force and audio.file_sha256(target) == item["sha256"].lower():
                continue
            _download(
                item["url"],
                target,
                item["sha256"],
                (lambda done, total, name=item["name"]: progress(name, done, total)) if progress else None,
            )

        weights = entry["weights"]
        weight_names = [weights] if isinstance(weights, str) else list(weights)
        hashes = {item["name"]: item["sha256"].lower() for item in files}
        manifest = Manifest(
            **entry,
            sha256=hashes[weight_names[0]] if len(weight_names) == 1 and not entry.get("config") else hashes,
            source={item["name"]: item["url"] for item in files},
        )
        (folder / MANIFEST).write_text(manifest.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        (folder / VERIFIED).unlink(missing_ok=True)
        self.scan()
        return self.get(model_id)

    def add(self, manifest: Manifest, files: dict[str, Path] | None = None, move: bool = False) -> Model:
        """
        Register a custom model.

        Args:
            manifest: The manifest to write. A missing sha256 is filled in from the files.
            files: File name in the model folder -> where the file is now. Files
                   already in the folder need not be listed.
            move: Move the files instead of copying them
        """
        folder = self.root / manifest.id
        if (folder / MANIFEST).exists():
            raise RegistryError(f"Model '{manifest.id}' already exists. Remove it first.")
        folder.mkdir(parents=True, exist_ok=True)
        for name, source in (files or {}).items():
            source = Path(source)
            if not source.is_file():
                raise RegistryError(f"File not found: {source}")
            target = folder / name
            if source.resolve() != target.resolve():
                (shutil.move if move else shutil.copy2)(str(source), str(target))

        model = Model(folder, manifest)
        missing = model.missing_files()
        if missing:
            raise RegistryError(f"Model '{manifest.id}' is incomplete: missing {', '.join(missing)}")
        if manifest.sha256 is None:
            hashes = model.hashes()
            weights = manifest.weight_files
            manifest = manifest.model_copy(
                update={"sha256": hashes[weights[0]] if len(weights) == 1 and not manifest.config else hashes}
            )
        (folder / MANIFEST).write_text(manifest.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        self.scan()
        return self.get(manifest.id)

    def remove(self, model_id: str) -> None:
        """Delete a model's folder."""
        folder = self.root / model_id
        if not ID_PATTERN.match(model_id) or not folder.is_dir():
            raise RegistryError(f"Model '{model_id}' is not installed.")
        shutil.rmtree(folder)
        self.scan()

    def catalog(self) -> list[dict]:
        """Installed models followed by curated ones that are not installed yet."""
        rows = [model.summary() for model in self.list()]
        installed = {row["id"] for row in rows}
        curated = load_curated()
        for row in rows:
            # Published scores belong to the curated list, which may know more than a
            # manifest written when it was fetched
            entry = curated.get(row["id"])
            if entry:
                row["curated"] = True
                for key in ("scores", "benchmark"):
                    if entry.get(key) and not row.get(key):
                        row[key] = entry[key]
        for model_id, entry in curated.items():
            if model_id not in installed:
                row = {key: value for key, value in entry.items() if key != "files"}
                row["installed"] = False
                row["curated"] = True
                row["download_bytes"] = sum(item.get("size", 0) for item in entry["files"])
                rows.append(row)
        return rows
