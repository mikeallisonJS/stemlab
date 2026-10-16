"""
Runs a recipe: sorts the graph, executes the nodes, caches intermediate stems
on disk and writes run.json beside the outputs.

Cancellation is cooperative: the flag is checked between chunks (inside the
backends) and between nodes. Exported files are staged and only moved into the
output folder once the whole run has succeeded, so a cancelled or failed run
leaves no partial outputs.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from stemlab import __version__, audio, paths
from stemlab.backends import base, device
from stemlab.backends.base import Cancelled
from stemlab.ops import analyze, ensemble, export, postprocess, separate, subtract
from stemlab.recipe import (
    MIX,
    OUTPUT_NAME,
    Recipe,
    RecipeError,
    node_references,
    split_reference,
)
from stemlab.registry import Registry

# Bump when a change makes previously cached stems wrong
CACHE_VERSION = 1

OPS = {
    "separate": separate,
    "subtract": subtract,
    "ensemble": ensemble,
    "postprocess": postprocess,
    "analyze": analyze,
    "export": export,
}

EventFn = Callable[[dict], None]


def replace(source: Path, target: Path, attempts: int = 25) -> None:
    """
    os.replace that waits out Windows: a virus scanner or the search indexer
    briefly holding a freshly written file makes the rename fail with "access denied".
    """
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.2)


# Cache ----------------------------------------------------------------------------


class Cache:
    """Intermediate stems on disk, one folder per node result, keyed by what produced it."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else paths.cache_dir()

    def folder(self, key: str) -> Path:
        return self.root / key[:2] / key

    def has(self, key: str) -> bool:
        return (self.folder(key) / "meta.json").is_file()

    def meta(self, key: str) -> dict:
        return json.loads((self.folder(key) / "meta.json").read_text(encoding="utf-8"))

    def stem_path(self, key: str, stem: str) -> Path:
        return self.folder(key) / f"{export.safe_name(stem)}.wav"

    def load(self, key: str, stem: str) -> np.ndarray:
        data, _rate = sf.read(str(self.stem_path(key, stem)), dtype="float32", always_2d=True)
        return np.ascontiguousarray(data.T)

    def store(self, key: str, stems: dict[str, np.ndarray], sample_rate: int, meta: dict) -> None:
        """Write a result. meta.json goes last and marks the entry as complete."""
        folder = self.folder(key)
        staging = folder.with_name(f"{folder.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:6]}")
        staging.mkdir(parents=True, exist_ok=True)
        try:
            for stem, data in stems.items():
                # 32-bit float keeps the stems exact, including samples beyond full scale
                sf.write(
                    str(staging / f"{export.safe_name(stem)}.wav"),
                    np.ascontiguousarray(data.T),
                    sample_rate,
                    subtype="FLOAT",
                    format="WAV",
                )
            (staging / "meta.json").write_text(
                json.dumps({**meta, "stems": list(stems), "sample_rate": sample_rate}, indent=2), encoding="utf-8"
            )
            if folder.exists():
                shutil.rmtree(folder, ignore_errors=True)
            replace(staging, folder)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def size(self) -> int:
        total = 0
        for root, _dirs, files in os.walk(self.root):
            total += sum(os.path.getsize(os.path.join(root, name)) for name in files)
        return total

    def clear(self) -> int:
        """Delete everything. Returns the number of bytes freed."""
        freed = self.size()
        for entry in self.root.iterdir():
            shutil.rmtree(entry, ignore_errors=True) if entry.is_dir() else entry.unlink(missing_ok=True)
        return freed


# Planning -------------------------------------------------------------------------


@dataclass
class NodePlan:
    """A node with everything resolved that is needed to run and to cache it."""

    name: str
    op: str
    node: Any
    #: Fully resolved parameters; what lands in run.json
    params: dict = field(default_factory=dict)
    model_id: str | None = None
    model_sha256: str | None = None
    backend: str | None = None
    #: postprocess: which of the model's stems becomes `out`
    keep: str | None = None
    #: Outputs other nodes may read
    outputs: list[str] = field(default_factory=list)
    #: Anything else the result depends on, such as the content of a reference file
    key_extra: dict = field(default_factory=dict)
    key: str = ""


def resolve_params(
    backend,
    registered,
    recipe_defaults: dict,
    node_params: dict,
    node_name: str,
    default_use: dict[str, dict] | None = None,
) -> dict:
    """
    Merge the layers of inference parameters, lowest priority first:
    backend defaults, device defaults, the model's config, the manifest's
    `defaults`, the recipe's `defaults`, then the node's own `params`.

    The recipe's defaults are shared by nodes on different backends, where a
    knob of the same name can mean different things (`overlap` is a count of
    chunks for msst and a fraction for demucs). A default that does not fit
    this node's backend is therefore skipped here; `default_use` collects
    where each one was applied so the caller can reject one that fits nowhere.
    """
    specs = backend.supported_params
    manifest_defaults = registered.manifest.defaults
    params = {name: spec.default for name, spec in specs.items()}

    requested = node_params.get("device", recipe_defaults.get("device", manifest_defaults.get("device", "auto")))
    try:
        resolved_device = backend.resolve_device(requested)
    except (RuntimeError, ValueError) as e:
        raise RecipeError(f"node '{node_name}': {e}") from None

    # Knobs this backend does not have are skipped: the layers also serve other backends
    layers = [
        ("device defaults", backend.device_defaults(resolved_device, device.vram_mb())),
        ("the model's config", backend.model_defaults(registered)),
        (f"the manifest of '{registered.id}'", manifest_defaults),
    ]
    for origin, layer in layers:
        for name, value in layer.items():
            if name in specs:
                try:
                    params[name] = specs[name].coerce(name, value)
                except ValueError as e:
                    raise RecipeError(f"node '{node_name}': {e} (from {origin})") from None

    for name, value in recipe_defaults.items():
        if name not in specs:
            continue
        use = default_use.setdefault(name, {"applied": [], "errors": []}) if default_use is not None else None
        try:
            params[name] = specs[name].coerce(name, value)
        except ValueError as e:
            if use is None:
                raise RecipeError(f"node '{node_name}': {e} (from the recipe's defaults)") from None
            use["errors"].append(f"node '{node_name}' ({backend.name}): {e}")
        else:
            if use is not None:
                use["applied"].append(node_name)

    for name, value in node_params.items():
        if name not in specs:
            raise RecipeError(
                f"node '{node_name}': '{name}' is not a parameter of the {backend.name} backend. "
                f"It supports: {', '.join(sorted(specs))}"
            )
        try:
            params[name] = specs[name].coerce(name, value)
        except ValueError as e:
            raise RecipeError(f"node '{node_name}': {e}") from None

    params["device"] = resolved_device
    if "dtype" in specs:
        params["dtype"] = device.resolve_dtype(params["dtype"], resolved_device)
    return params


def plan_recipe(recipe: Recipe, registry: Registry) -> dict[str, NodePlan]:
    """
    Check a recipe against the installed models and resolve every node.
    Raises RecipeError with a message naming the node at fault.
    """
    plans: dict[str, NodePlan] = {}
    default_use: dict[str, dict] = {}
    for name in recipe.order():
        node = recipe.nodes[name]
        plan = NodePlan(name=name, op=node.op, node=node)

        if node.op in ("separate", "postprocess"):
            try:
                registered = registry.get(node.model)
            except Exception as e:
                raise RecipeError(f"node '{name}': {e}") from None
            manifest = registered.manifest
            try:
                backend = base.get_backend(manifest.backend)
                plan.params = resolve_params(backend, registered, recipe.defaults, node.params, name, default_use)
                plan.model_sha256 = registered.sha256()
            except RecipeError:
                raise
            except Exception as e:
                raise RecipeError(f"node '{name}': {e}") from None
            plan.model_id = manifest.id
            plan.backend = manifest.backend

            if node.op == "separate":
                targets = node.targets if node.targets is not None else list(manifest.stems)
                unknown = [stem for stem in targets if stem not in manifest.stems]
                if unknown:
                    raise RecipeError(
                        f"node '{name}': model '{manifest.id}' has no stem {unknown}. Its stems are {manifest.stems}"
                    )
                plan.outputs = list(targets)
            else:
                keep = node.target or manifest.stems[0]
                if keep not in manifest.stems:
                    raise RecipeError(
                        f"node '{name}': model '{manifest.id}' has no stem '{keep}'. Its stems are {manifest.stems}"
                    )
                plan.keep = keep
                plan.outputs = ["out"]
        else:
            plan.params = node.params.model_dump(mode="json")
            plan.outputs = [OUTPUT_NAME[node.op]] if node.op in OUTPUT_NAME else []

        for reference in node_references(node):
            source, stem = split_reference(reference)
            if source != MIX and stem not in plans[source].outputs:
                raise RecipeError(
                    f"node '{name}' reads '{reference}', but '{source}' only emits {plans[source].outputs}"
                )
        plans[name] = plan

    # A default may be skipped by backends it does not fit, but it has to fit at least one node
    for name, use in default_use.items():
        if use["errors"] and not use["applied"]:
            raise RecipeError(f"defaults.{name} fits no node: " + "; ".join(use["errors"]))
    return plans


def _digest(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def assign_keys(plans: dict[str, NodePlan], mix_key: str) -> None:
    """
    Give every node a cache key from its parameters, its model and the keys of
    its inputs. `targets` is left out for separate nodes: all stems are cached,
    so asking for different ones reuses the same entry.
    """
    for plan in plans.values():
        inputs = []
        for reference in node_references(plan.node):
            source, stem = split_reference(reference)
            inputs.append(mix_key if source == MIX else f"{plans[source].key}:{stem}")
        plan.key = _digest(
            {
                "v": CACHE_VERSION,
                "op": plan.op,
                "params": plan.params,
                "model": plan.model_sha256,
                "keep": plan.keep,
                "inputs": inputs,
                "extra": plan.key_extra,
            }
        )


# Running --------------------------------------------------------------------------


class RunContext:
    """What the node operations see of a run in progress."""

    def __init__(
        self,
        recipe: Recipe,
        plans: dict[str, NodePlan],
        mix: np.ndarray,
        sample_rate: int,
        track: str,
        input_path: Path,
        registry: Registry,
        cache: Cache,
        staging: Path,
        emit: EventFn,
        cancel: Any,
    ):
        self.recipe = recipe
        self.plans = plans
        self.sample_rate = sample_rate
        self.track = track
        self.input_path = input_path
        self.registry = registry
        self.cache = cache
        self.staging = staging
        self.emit = emit
        self.cancel = cancel
        self._stems: dict[tuple[str, str], np.ndarray] = {(MIX, MIX): mix}
        self._model = None
        self._model_identity: tuple | None = None

    def audio(self, reference: str) -> np.ndarray:
        """The audio behind `mix` or `node.stem`, loaded from the cache when needed."""
        source, stem = split_reference(reference)
        if (source, stem) not in self._stems:
            self._stems[(source, stem)] = self.cache.load(self.plans[source].key, stem)
        return self._stems[(source, stem)]

    def remember(self, name: str, stems: dict[str, np.ndarray]) -> None:
        for stem, data in stems.items():
            self._stems[(name, stem)] = data

    def model(self, plan: NodePlan):
        """The loaded model for a node. One model is kept in memory at a time."""
        identity = (plan.model_id, plan.params.get("device"))
        if self._model_identity != identity:
            self.close_model()
            self.emit({"type": "node_status", "node": plan.name, "status": f"Loading {plan.model_id}"})
            backend = base.get_backend(plan.backend)
            self._model = backend.load(self.registry.get(plan.model_id), plan.params)
            self._model_identity = identity
        return self._model

    def close_model(self) -> None:
        if self._model is not None:
            try:
                self._model.close()
            finally:
                self._model = None
                self._model_identity = None

    def progress(self, name: str) -> Callable[[float], None]:
        last = [-1.0]

        def report(fraction: float) -> None:
            fraction = max(0.0, min(1.0, float(fraction)))
            # At most one event per percent
            if fraction - last[0] >= 0.01 or fraction >= 1.0 > last[0]:
                last[0] = fraction
                self.emit({"type": "node_progress", "node": name, "fraction": round(fraction, 4)})

        return report

    def warn(self, name: str, message: str) -> None:
        self.emit({"type": "warning", "node": name, "message": message})

    def check_cancel(self) -> None:
        base.check_cancel(self.cancel)

    def resolve_path(self, path: str) -> Path:
        """Relative paths in a recipe are taken relative to the input file."""
        candidate = Path(path).expanduser()
        return candidate if candidate.is_absolute() else self.input_path.parent / candidate


def default_output_dir(input_path: Path, recipe: Recipe, parent: Path | None = None) -> Path:
    """
    `<parent>/<track> [<recipe>]`, next to the input by default.

    Two different files can share a name ("song.wav" in two folders, or next
    to "song.flac"). A folder already holding the run of another input is
    left alone and a numbered one is used instead; running the same file
    again replaces its own earlier results.
    """
    base = Path(parent) if parent else input_path.parent
    name = export.safe_name(f"{input_path.stem} [{recipe.name}]")
    number = 1
    while True:
        candidate = base / (name if number == 1 else f"{name} ({number})")
        try:
            previous = json.loads((candidate / "run.json").read_text(encoding="utf-8"))["input"]["path"]
        except (OSError, ValueError, KeyError, TypeError):
            return candidate
        if os.path.normcase(previous) == os.path.normcase(str(input_path.resolve())):
            return candidate
        number += 1


def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def run_recipe(
    recipe: Recipe,
    input_path: str | os.PathLike,
    out_dir: str | os.PathLike | None = None,
    *,
    registry: Registry | None = None,
    events: EventFn | None = None,
    cancel: Any = None,
    use_cache: bool = True,
    cache: Cache | None = None,
    on_mix: Callable[[str], None] | None = None,
    out_parent: str | os.PathLike | None = None,
) -> dict:
    """
    Run a recipe on one audio file.

    Args:
        recipe: The validated recipe
        input_path: The audio file; it is the implicit `mix` node
        out_dir: Where exported files and run.json go. When omitted, a folder named
                 after the track and the recipe is used, below `out_parent`
        out_parent: Where that folder is created; next to the input by default
        registry: Installed models (the default registry when omitted)
        events: Called with a dict for every step: run_started, node_started,
                node_status, node_progress, node_finished, warning, run_finished,
                run_cancelled, run_failed
        cancel: Object with `is_set()`; set it to stop the run
        use_cache: Reuse cached intermediate stems
        on_mix: Called with the path of the decoded input once it is available,
                so a client can play it while the run is still going

    Returns:
        The run record, which is also written to `<out_dir>/run.json`

    Raises:
        Cancelled: the run was cancelled; no output files were written
        RecipeError: the recipe does not fit the installed models
    """
    emit: EventFn = events or (lambda event: None)
    registry = registry or Registry()
    cache = cache or Cache()
    input_path = Path(input_path).resolve()
    run_id = uuid.uuid4().hex[:12]
    started = time.time()

    plans = plan_recipe(recipe, registry)
    base.check_cancel(cancel)

    mix, sample_rate = audio.load(input_path)
    source_channels = mix.shape[0]
    # Models work on stereo; a mono file is duplicated so that subtract stays sample-exact
    mix = audio.to_channels(mix, 2)
    input_sha256 = audio.file_sha256(input_path)
    mix_key = _digest({"v": CACHE_VERSION, "file": input_sha256, "sample_rate": sample_rate, "channels": 2})
    for plan in plans.values():
        reference = getattr(plan.node.params, "reference", None) if plan.op == "analyze" else None
        if reference:
            candidate = Path(reference).expanduser()
            resolved = candidate if candidate.is_absolute() else input_path.parent / candidate
            if not resolved.is_file():
                raise RecipeError(f"node '{plan.name}': reference file not found: {resolved}")
            # The score depends on what is in the file, not on what it is called
            plan.key_extra = {"reference_sha256": audio.file_sha256(resolved)}
    assign_keys(plans, mix_key)

    out_dir = (
        Path(out_dir) if out_dir else default_output_dir(input_path, recipe, Path(out_parent) if out_parent else None)
    )
    staging = out_dir / f".staging-{run_id}"
    record: dict = {
        "stemlab": __version__,
        "run_id": run_id,
        "status": "running",
        "started": _now(),
        "input": {
            "path": str(input_path),
            "sha256": input_sha256,
            "sample_rate": sample_rate,
            "channels": source_channels,
            "duration": round(mix.shape[-1] / sample_rate, 3),
        },
        "output_dir": str(out_dir),
        "recipe": recipe.model_dump(mode="json", exclude_defaults=True)
        | {"version": recipe.version, "name": recipe.name},
        "system": {},
        "backends": {},
        "models": {},
        "mix": {},
        "nodes": {},
        "outputs": [],
        "warnings": [],
    }

    def tracked_emit(event: dict) -> None:
        if event.get("type") == "warning":
            record["warnings"].append({"node": event.get("node"), "message": event.get("message")})
        emit({**event, "run_id": run_id})

    ctx = RunContext(
        recipe, plans, mix, sample_rate, input_path.stem, input_path, registry, cache, staging, tracked_emit, cancel
    )
    order = list(plans)
    tracked_emit(
        {
            "type": "run_started",
            "recipe": recipe.name,
            "input": str(input_path),
            "nodes": order,
            "output_dir": str(out_dir),
        }
    )

    try:
        # The mix is cached like any stem so the UI can play and analyze it
        if not cache.has(mix_key):
            cache.store(mix_key, {MIX: mix}, sample_rate, {"op": MIX, "source": str(input_path)})
        record["mix"] = {"cache_key": mix_key, "file": str(cache.stem_path(mix_key, MIX))}
        if on_mix is not None:
            on_mix(record["mix"]["file"])

        for name in order:
            base.check_cancel(cancel)
            plan = plans[name]
            node_started = time.time()
            tracked_emit({"type": "node_started", "node": name, "op": plan.op, "model": plan.model_id})
            entry: dict = {"op": plan.op, "params": plan.params, "cache_key": plan.key, "cached": False}
            if plan.model_id:
                entry["model"] = plan.model_id
                registered = registry.get(plan.model_id)
                record["models"].setdefault(
                    plan.model_id,
                    {
                        "sha256": plan.model_sha256,
                        "backend": plan.backend,
                        "arch": registered.manifest.arch,
                        "files": registered.hashes(),
                    },
                )
                record["backends"].setdefault(plan.backend, base.get_backend(plan.backend).version())

            cacheable = plan.op != "export"
            if cacheable and use_cache and cache.has(plan.key):
                meta = cache.meta(plan.key)
                entry["cached"] = True
                entry["info"] = meta.get("info", {})
            else:
                result = OPS[plan.op].run(ctx, name, plan.node, plan)
                base.check_cancel(cancel)
                entry["info"] = result.info
                if cacheable:
                    cache.store(
                        plan.key,
                        result.stems,
                        sample_rate,
                        {"op": plan.op, "model": plan.model_id, "params": plan.params, "info": result.info},
                    )
                    ctx.remember(name, result.stems)

            if plan.op == "export":
                for item in entry["info"].get("files", []):
                    record["outputs"].append({**item, "node": name})
            entry["stems"] = {stem: str(cache.stem_path(plan.key, stem)) for stem in plan.outputs}
            entry["seconds"] = round(time.time() - node_started, 3)
            record["nodes"][name] = entry
            tracked_emit(
                {
                    "type": "node_finished",
                    "node": name,
                    "op": plan.op,
                    "cached": entry["cached"],
                    "seconds": entry["seconds"],
                    "stems": entry["stems"],
                    "info": entry["info"],
                }
            )

        base.check_cancel(cancel)
        ctx.close_model()

        # Everything succeeded: move the exported files into place
        out_dir.mkdir(parents=True, exist_ok=True)
        if staging.is_dir():
            for item in staging.iterdir():
                replace(item, out_dir / item.name)
        for output in record["outputs"]:
            output["path"] = str(out_dir / output["file"])

        info = device.system_info()
        record["system"] = {
            "os": info.os,
            "machine": info.machine,
            "python": info.python,
            "gpu": info.gpu,
            "vram_mb": info.vram_mb,
            "torch_flavor": info.flavor,
        }
        record["status"] = "finished"
        record["finished"] = _now()
        record["seconds"] = round(time.time() - started, 3)
        (out_dir / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        tracked_emit(
            {
                "type": "run_finished",
                "seconds": record["seconds"],
                "outputs": record["outputs"],
                "run_json": str(out_dir / "run.json"),
            }
        )
        return record
    except Cancelled:
        tracked_emit({"type": "run_cancelled"})
        raise
    except Exception as e:
        tracked_emit({"type": "run_failed", "error": str(e) or type(e).__name__})
        raise
    finally:
        ctx.close_model()
        shutil.rmtree(staging, ignore_errors=True)
        # Do not leave an empty output folder behind after a failed first run
        try:
            if out_dir.is_dir() and not any(out_dir.iterdir()):
                out_dir.rmdir()
        except OSError:
            pass


def recipe_from_run(record: dict) -> Recipe:
    """
    Rebuild the recipe of a finished run with every parameter pinned to the
    value it resolved to, so the run can be repeated exactly.
    """
    from stemlab.recipe import parse

    data = json.loads(json.dumps(record["recipe"]))
    data.pop("defaults", None)
    for name, entry in record.get("nodes", {}).items():
        if entry["op"] in ("separate", "postprocess") and name in data.get("nodes", {}):
            data["nodes"][name]["params"] = dict(entry["params"])
    return parse(data)
