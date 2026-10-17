"""
The local API the UI talks to.

    POST /jobs                  run a recipe on one or more files
    GET  /jobs, /jobs/{id}      job state
    WS   /jobs/{id}/events      per-node and per-chunk progress, replayed from the start
    GET/POST /models            the registry
    GET  /system                GPU, VRAM, backend versions

The server only ever listens on the local machine. Everything that runs a
model goes through the job queue and the runner.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import string
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from stemlab import __version__, audio, bootstrap, dsp, paths, runner
from stemlab import recipe as recipe_module
from stemlab.backends import base, device
from stemlab.recipe import RecipeError
from stemlab.registry import Manifest, Registry, RegistryError, load_curated
from stemlab.server.jobs import JobManager

UI_DIST = paths.REPO_ROOT / "app" / "dist"
RECIPES_DIR = paths.REPO_ROOT / "recipes"

AUDIO_EXTENSIONS = {
    ".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif", ".wma", ".mp4", ".mkv", ".mov", ".webm",
}  # fmt: skip

# What each op takes and gives, for drawing nodes. Parameters come from the JSON Schema.
OPS = {
    "separate": {"inputs": [{"name": "audio", "many": False}], "outputs": "model", "model": True},
    "subtract": {"inputs": [{"name": "a", "many": False}, {"name": "b", "many": False}], "outputs": ["out"]},
    "ensemble": {"inputs": [{"name": "inputs", "many": True}], "outputs": ["out"]},
    "postprocess": {"inputs": [{"name": "audio", "many": False}], "outputs": ["out"], "model": True},
    "analyze": {"inputs": [{"name": "mix", "many": False}, {"name": "stems", "many": True}], "outputs": ["residual"]},
    "export": {"inputs": [{"name": "inputs", "many": True}], "outputs": []},
}


class JobRequest(BaseModel):
    recipe: dict[str, Any] | None = Field(None, description="The recipe as data")
    recipe_yaml: str | None = Field(None, description="The recipe as YAML text, instead of `recipe`")
    inputs: list[str] = Field(min_length=1, description="Paths of the audio files to process")
    out_dir: str | None = Field(None, description="Output folder; next to each input when omitted")
    use_cache: bool = True


class RecipeText(BaseModel):
    yaml: str


class RecipeData(BaseModel):
    recipe: dict[str, Any]


class AddModelRequest(BaseModel):
    manifest: dict[str, Any]
    files: dict[str, str] = Field(default_factory=dict, description="File name in the registry -> current path")
    move: bool = False


class SystemConfig(BaseModel):
    """The Doctor screen's overrides. None means "as detected"."""

    torch_flavor: str | None = None
    rocm_target: str | None = None


class OpenRunRequest(BaseModel):
    path: str


def _parse_recipe(body: JobRequest | RecipeData | RecipeText):
    try:
        if isinstance(body, RecipeText):
            return recipe_module.loads(body.yaml)
        if isinstance(body, RecipeData):
            return recipe_module.parse(body.recipe)
        if body.recipe is not None:
            return recipe_module.parse(body.recipe)
        if body.recipe_yaml is not None:
            return recipe_module.loads(body.recipe_yaml)
    except RecipeError as e:
        raise HTTPException(422, str(e)) from None
    raise HTTPException(422, "Send either `recipe` or `recipe_yaml`")


def _preview(path: str) -> Path:
    """
    A 16-bit FLAC copy of a cached stem for the browser: a quarter of the
    size of the float WAV the engine keeps, and playable everywhere.
    """
    source = Path(path)
    preview = source.with_suffix(".preview.flac")
    if not preview.is_file() or preview.stat().st_mtime < source.stat().st_mtime:
        data, rate = sf.read(str(source), dtype="float32", always_2d=True)
        partial = preview.with_suffix(".part")
        sf.write(str(partial), np.clip(data, -1.0, 1.0), rate, subtype="PCM_16", format="FLAC")
        runner.replace(partial, preview)
    return preview


LOCAL_HOSTS = ["127.0.0.1", "localhost", "[::1]"]
# Dropped files are kept this long, so their runs can be repeated for a while
UPLOAD_DAYS = 7


def clean_uploads(max_age_days: float = UPLOAD_DAYS) -> int:
    """Delete dropped files that have not been touched for a while. Returns how many folders went."""
    removed = 0
    limit = time.time() - max_age_days * 86400
    for folder in paths.uploads_dir().iterdir():
        try:
            newest = max((item.stat().st_mtime for item in folder.rglob("*")), default=folder.stat().st_mtime)
            if newest < limit:
                shutil.rmtree(folder, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed


def create_app(
    manager: JobManager | None = None,
    dev_origins: list[str] | None = None,
    allowed_hosts: list[str] | None = None,
) -> FastAPI:
    """
    Build the API.

    Args:
        manager: The job queue (a new one by default)
        dev_origins: Extra origins allowed to read the API, besides local ones
        allowed_hosts: Host names requests may be addressed to. Local names only by
                       default, which keeps other websites from reaching the API
                       through DNS rebinding; `serve --host` adds the address it binds
    """
    jobs = manager or JobManager()
    clean_uploads()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        jobs.shutdown()

    app = FastAPI(title="Stemlab", version=__version__, lifespan=lifespan)
    # Local only: refuse requests addressed to any other host name (DNS rebinding)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or LOCAL_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_origins=dev_origins or [],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.jobs = jobs

    def job_or_404(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, f"No job {job_id}")
        return job

    def stem_or_404(job_id: str, node: str, stem: str) -> str:
        path = job_or_404(job_id).stem_file(node, stem)
        if not path or not Path(path).is_file():
            raise HTTPException(404, f"{node}.{stem} is not available (yet)")
        return path

    # System ---------------------------------------------------------------------

    @app.get("/system")
    def system() -> dict:
        info = device.system_info().to_dict()
        info["version"] = __version__
        info["cache_bytes"] = runner.Cache().size()
        info["outputs_dir"] = str(paths.outputs_dir())
        # What `stemlab bootstrap` would run for the chosen flavor, for the Doctor screen
        try:
            info["bootstrap"] = {"commands": [" ".join(command) for command in bootstrap.plan(info["flavor"])]}
        except ValueError as e:
            info["bootstrap"] = {"error": str(e)}
        return info

    @app.put("/system/config")
    def set_system_config(body: SystemConfig) -> dict:
        """Override the torch flavor and, on Windows ROCm, the GPU target; null restores detection."""
        if body.torch_flavor is not None and body.torch_flavor not in device.FLAVORS:
            raise HTTPException(400, f"Unknown flavor '{body.torch_flavor}'. Use one of {', '.join(device.FLAVORS)}.")
        if body.rocm_target is not None and not body.rocm_target.startswith("gfx"):
            raise HTTPException(400, f"Unknown ROCm target '{body.rocm_target}'. Use a gfx name such as gfx1151.")
        device.write_config(torch_flavor=body.torch_flavor, rocm_target=body.rocm_target)
        return system()

    @app.get("/schema")
    def schema() -> dict:
        """Everything the UI needs to build forms: the recipe schema, the ops and each backend's knobs."""
        backends = {}
        for name in base.BACKENDS:
            try:
                backends[name] = recipe_module.backend_param_schema(base.supported_params(name))
            except Exception as e:
                backends[name] = {"error": str(e)}
        return {
            "recipe": recipe_module.json_schema(),
            "ops": OPS,
            "backends": backends,
            "export_formats": list(audio.EXPORT_FORMATS),
        }

    # Recipes --------------------------------------------------------------------

    @app.get("/recipes")
    def list_recipes() -> list[dict]:
        """The example recipes shipped with the application."""
        found = []
        for path in sorted(RECIPES_DIR.glob("*.yaml")):
            text = path.read_text(encoding="utf-8")
            try:
                parsed = recipe_module.loads(text)
            except RecipeError:
                continue
            found.append({"file": path.name, "name": parsed.name, "yaml": text, "nodes": len(parsed.nodes)})
        return found

    @app.post("/recipes/parse")
    def parse_recipe(body: RecipeText) -> dict:
        """YAML text -> recipe data, with defaults left out."""
        parsed = _parse_recipe(body)
        return {"recipe": parsed.model_dump(mode="json", exclude_defaults=True) | {"name": parsed.name}}

    @app.post("/recipes/yaml")
    def recipe_yaml(body: RecipeData) -> dict:
        """Recipe data -> YAML text."""
        return {"yaml": _parse_recipe(body).to_yaml()}

    @app.post("/recipes/validate")
    def validate_recipe(body: RecipeData) -> dict:
        """Check a recipe against the installed models and return every node's resolved parameters."""
        parsed = _parse_recipe(body)
        try:
            plans = runner.plan_recipe(parsed, Registry())
        except RecipeError as e:
            return {"ok": False, "error": str(e)}
        return {
            "ok": True,
            "order": list(plans),
            "nodes": {
                name: {"op": plan.op, "model": plan.model_id, "params": plan.params, "outputs": plan.outputs}
                for name, plan in plans.items()
            },
        }

    # Models ---------------------------------------------------------------------

    @app.get("/models")
    def list_models() -> dict:
        registry = Registry()
        return {"root": str(registry.root), "models": registry.catalog(), "problems": registry.problems}

    @app.post("/models", status_code=201)
    def add_model(body: AddModelRequest) -> dict:
        """Register a custom model from files on this machine."""
        try:
            manifest = Manifest.model_validate(body.manifest)
            model = Registry().add(manifest, {name: Path(path) for name, path in body.files.items()}, move=body.move)
        except RegistryError as e:
            raise HTTPException(409, str(e)) from None
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        return model.summary()

    @app.post("/models/{model_id}/fetch")
    def fetch_model(model_id: str) -> dict:
        """Download a curated model and verify it. Blocks until done."""
        if model_id not in load_curated():
            raise HTTPException(404, f"'{model_id}' is not a curated model")
        try:
            return Registry().fetch(model_id).summary()
        except (RegistryError, OSError) as e:
            raise HTTPException(502, str(e)) from None

    @app.delete("/models/{model_id}", status_code=204)
    def remove_model(model_id: str) -> Response:
        try:
            Registry().remove(model_id)
        except RegistryError as e:
            raise HTTPException(404, str(e)) from None
        return Response(status_code=204)

    # Jobs -----------------------------------------------------------------------

    @app.post("/jobs", status_code=201)
    def create_jobs(body: JobRequest) -> list[dict]:
        """Queue the recipe once per input file."""
        parsed = _parse_recipe(body)
        inputs = [Path(item).expanduser() for item in body.inputs]
        missing = [str(path) for path in inputs if not path.is_file()]
        if missing:
            raise HTTPException(404, "File not found: " + ", ".join(missing))
        try:
            runner.plan_recipe(parsed, Registry())
        except RecipeError as e:
            raise HTTPException(422, str(e)) from None

        chosen = Path(body.out_dir).expanduser() if body.out_dir else None
        uploads = paths.uploads_dir().resolve()
        created = []
        for path in inputs:
            path = path.resolve()
            out_dir = out_parent = None
            if chosen is not None and len(inputs) == 1:
                out_dir = chosen
            elif chosen is not None:
                out_parent = chosen
            elif uploads in path.parents:
                # A dropped file lives in the app's data folder; "next to the input" would bury its stems there
                out_parent = paths.outputs_dir()
            created.append(jobs.submit(parsed, path, out_dir, body.use_cache, out_parent).summary())
        return created

    @app.get("/jobs")
    def list_jobs() -> list[dict]:
        return [job.summary() for job in jobs.list()]

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        return job_or_404(job_id).detail()

    @app.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict:
        job = job_or_404(job_id)
        jobs.cancel(job_id)
        return job.summary()

    @app.delete("/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str) -> Response:
        job = job_or_404(job_id)
        if not job.done:
            raise HTTPException(409, "The job is still running; cancel it first")
        jobs.remove(job_id)
        return Response(status_code=204)

    @app.post("/runs/open", status_code=201)
    def open_run(body: OpenRunRequest) -> dict:
        """Load a finished run from its run.json (or the folder containing it)."""
        path = Path(body.path).expanduser()
        if path.is_dir():
            path = path / "run.json"
        if not path.is_file():
            raise HTTPException(404, f"File not found: {path}")
        try:
            return jobs.open_run(path).detail()
        except (ValueError, KeyError, RecipeError) as e:
            raise HTTPException(422, f"Cannot open {path}: {e}") from None

    @app.websocket("/jobs/{job_id}/events")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        job = jobs.get(job_id)
        if job is None:
            await websocket.close(code=4404)
            return
        await websocket.accept()
        queue, history = job.subscribe(asyncio.get_running_loop())
        try:
            for event in history:
                await websocket.send_json(event)
            finished = any(event["type"] == "job_done" for event in history)
            while not finished:
                event = await queue.get()
                await websocket.send_json(event)
                finished = event["type"] == "job_done"
            await websocket.close()
        except WebSocketDisconnect:
            pass
        finally:
            job.unsubscribe(queue)

    # Audio of a job's stems -----------------------------------------------------

    @app.get("/jobs/{job_id}/audio/{node}/{stem}")
    def stem_audio(job_id: str, node: str, stem: str) -> FileResponse:
        """The stem as FLAC. `mix/mix` is the input file."""
        preview = _preview(stem_or_404(job_id, node, stem))
        return FileResponse(preview, media_type="audio/flac", filename=f"{node}.{stem}.flac")

    @app.get("/jobs/{job_id}/peaks/{node}/{stem}")
    def stem_peaks(job_id: str, node: str, stem: str, buckets: int = Query(2000, ge=10, le=20000)) -> dict:
        """Min/max envelope for drawing the waveform without downloading the audio."""
        data, rate = sf.read(stem_or_404(job_id, node, stem), dtype="float32", always_2d=True)
        return {
            "peaks": dsp.peaks(data.T, buckets),
            "duration": len(data) / rate,
            "sample_rate": rate,
            "rms_db": round(dsp.rms_db(data), 2),
            "peak_db": round(dsp.peak_db(data), 2),
        }

    @app.get("/jobs/{job_id}/spectrogram/{node}/{stem}")
    def stem_spectrogram(
        job_id: str,
        node: str,
        stem: str,
        width: int = Query(1200, ge=100, le=4000),
        height: int = Query(256, ge=64, le=1024),
    ) -> Response:
        """Log-frequency spectrogram as a PNG image."""
        data, rate = sf.read(stem_or_404(job_id, node, stem), dtype="float32", always_2d=True)
        image = dsp.spectrogram_image(data.T, rate, width, height)
        return Response(dsp.png_bytes(image), media_type="image/png", headers={"Cache-Control": "max-age=3600"})

    # Choosing input files -------------------------------------------------------

    @app.get("/fs")
    def browse(path: str | None = None) -> dict:
        """List a folder on this machine, so a browser can pick input files by path."""
        if not path:
            roots = [str(Path.home())]
            if sys.platform == "win32":
                roots += [f"{letter}:\\" for letter in string.ascii_uppercase if Path(f"{letter}:\\").exists()]
            else:
                roots.append("/")
            return {"path": None, "parent": None, "folders": [{"name": r, "path": r} for r in roots], "files": []}
        folder = Path(path).expanduser()
        if not folder.is_dir():
            raise HTTPException(404, f"Not a folder: {folder}")
        folders, files = [], []
        try:
            for entry in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
                if entry.name.startswith("."):
                    continue
                try:
                    if entry.is_dir():
                        folders.append({"name": entry.name, "path": str(entry)})
                    elif entry.suffix.lower() in AUDIO_EXTENSIONS or entry.name == "run.json":
                        files.append({"name": entry.name, "path": str(entry), "size": entry.stat().st_size})
                except OSError:
                    continue
        except OSError as e:
            raise HTTPException(403, f"Cannot read {folder}: {e}") from None
        parent = str(folder.parent) if folder.parent != folder else None
        return {"path": str(folder), "parent": parent, "folders": folders, "files": files}

    @app.post("/uploads", status_code=201)
    async def upload(request: Request, name: str = Query(..., min_length=1, max_length=255)) -> dict:
        """
        Store a dropped file so it can be used as an input. A browser cannot
        tell the server where a dropped file lives, so it sends the bytes.
        """
        safe = Path(name).name
        if Path(safe).suffix.lower() not in AUDIO_EXTENSIONS:
            raise HTTPException(415, f"'{safe}' is not an audio file")
        folder = paths.uploads_dir() / hashlib.sha256(os.urandom(16)).hexdigest()[:12]
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / safe
        size = 0
        with open(target, "wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                f.write(chunk)
        if size == 0:
            target.unlink(missing_ok=True)
            raise HTTPException(400, "The upload was empty")
        try:
            details = audio.info(target)
        except Exception:
            target.unlink(missing_ok=True)
            raise HTTPException(415, f"'{safe}' could not be read as audio") from None
        return {"path": str(target), "name": safe, "size": size, "uploaded": True, **details}

    @app.get("/audio/info")
    def audio_info(path: str) -> dict:
        target = Path(path).expanduser()
        if not target.is_file():
            raise HTTPException(404, f"File not found: {target}")
        try:
            return {"path": str(target), "name": target.name, "size": target.stat().st_size, **audio.info(target)}
        except Exception as e:
            raise HTTPException(415, f"'{target.name}' could not be read as audio: {e}") from None

    # The built UI, when present. In development Vite serves it instead.
    if UI_DIST.is_dir():
        app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")

    return app
