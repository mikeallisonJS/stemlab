"""The `captainstems` command line."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from captainstems import __version__

app = typer.Typer(help="Recipe-driven stem separation.", no_args_is_help=True, add_completion=False)
console = Console()


def _fail(message: str, code: int = 1) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code)


@app.command()
def doctor(
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
    set_flavor: str = typer.Option(
        None, "--set-flavor", help="Override the torch flavor: cuda, rocm, mps, cpu or auto"
    ),
) -> None:
    """Show the detected OS, GPU, torch flavor and backend versions."""
    from captainstems import bootstrap
    from captainstems.backends import device

    if set_flavor is not None:
        if set_flavor == "auto":
            device.write_config(torch_flavor=None)
        elif set_flavor in device.FLAVORS:
            device.write_config(torch_flavor=set_flavor)
        else:
            _fail(f"Unknown flavor '{set_flavor}'. Use cuda, rocm, mps, cpu or auto.", 2)

    info = device.system_info()
    if as_json:
        print(json.dumps(info.to_dict(), indent=2))
        return

    table = Table(title=f"CaptainStems {__version__}", show_header=False, title_justify="left")
    table.add_column(style="bold")
    table.add_column()
    table.add_row("OS", f"{info.os} {info.os_version} ({info.machine})")
    table.add_row("Python", info.python)
    table.add_row(
        "GPU", f"{info.gpu} ({info.vram_mb} MiB)" if info.gpu and info.vram_mb else (info.gpu or "none detected")
    )
    flavor = (
        info.flavor
        if info.flavor_source == "detected"
        else f"{info.flavor} (override; detected {info.detected_flavor})"
    )
    table.add_row("Torch flavor", flavor)

    torch = info.torch
    if torch["version"]:
        runs_on = "CUDA" if torch["cuda"] else ("MPS" if torch["mps"] else "CPU only")
        table.add_row("torch", f"{torch['version']} - {runs_on}")
    else:
        table.add_row("torch", "[yellow]not installed[/yellow]")
    onnx = info.onnxruntime
    if onnx["version"]:
        table.add_row(
            "onnxruntime",
            f"{onnx['version']} - {', '.join(p.replace('ExecutionProvider', '') for p in onnx['providers'])}",
        )
    else:
        table.add_row("onnxruntime", "[yellow]not installed[/yellow]")
    table.add_row("FFmpeg", info.ffmpeg or "[yellow]not found[/yellow]")
    for name, version in info.backends.items():
        if "error" in version:
            table.add_row(f"backend {name}", f"[yellow]unavailable[/yellow]: {version['error']}")
        else:
            table.add_row(f"backend {name}", ", ".join(f"{key} {value}" for key, value in version.items()))
    table.add_row("Data folder", info.home)
    console.print(table)

    expected_cuda = info.flavor == "cuda"
    if not torch["version"] or (expected_cuda and not torch["cuda"]):
        console.print("\nThe model libraries are missing or do not match the GPU. Install them with:")
        console.print("  [bold]captainstems bootstrap[/bold]\nwhich runs:")
        for command in bootstrap.plan(info.flavor):
            console.print("  " + " ".join(command), highlight=False, soft_wrap=True)


@app.command("bootstrap")
def bootstrap_command(
    flavor: str = typer.Option(None, "--flavor", help="cuda, rocm, mps or cpu; default is the detected one"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only print the commands"),
) -> None:
    """Install torch for this machine's GPU, the model libraries and onnxruntime."""
    from captainstems import bootstrap
    from captainstems.backends import device

    chosen = flavor or device.chosen_flavor()[0]
    try:
        commands = bootstrap.plan(chosen)
    except ValueError as e:
        _fail(str(e), 2)
    if dry_run:
        for command in commands:
            print(" ".join(command))
        return
    console.print(f"Installing the [bold]{chosen}[/bold] flavor into {sys.prefix}")
    if not bootstrap.run(chosen, log=lambda line: console.print(line, highlight=False, soft_wrap=True)):
        _fail("Bootstrap failed. The command above can be rerun by hand.")
    console.print("[green]Done.[/green] Run [bold]captainstems doctor[/bold] to check the result.")


# Running recipes ------------------------------------------------------------------


def _load_recipe(path: Path):
    """A recipe YAML, or the run.json of an earlier run (repeats it with its exact parameters)."""
    from captainstems import recipe as recipe_module
    from captainstems import runner

    if path.suffix.lower() == ".json":
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise recipe_module.RecipeError(f"Cannot read {path}: {e}") from None
        if "recipe" not in record:
            raise recipe_module.RecipeError(f"{path} is not a run.json")
        return runner.recipe_from_run(record)
    return recipe_module.load(path)


@app.command()
def run(
    recipe_path: Path = typer.Argument(..., metavar="RECIPE", help="Recipe YAML, or a run.json to repeat"),
    inputs: list[Path] = typer.Argument(..., metavar="AUDIO...", help="Audio files to process"),
    out: Path = typer.Option(None, "--out", "-o", help="Output folder (with several inputs: its parent)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Recompute every node"),
    events: bool = typer.Option(False, "--events", help="Print one JSON event per line instead of progress bars"),
) -> None:
    """Run a recipe on one or more audio files."""
    from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

    from captainstems import recipe as recipe_module
    from captainstems import runner
    from captainstems.audio import AudioError
    from captainstems.backends.base import BackendError, Cancelled
    from captainstems.registry import Registry, RegistryError

    try:
        recipe = _load_recipe(recipe_path)
    except recipe_module.RecipeError as e:
        _fail(str(e), 2)

    registry = Registry()
    failures = 0
    for input_path in inputs:
        out_dir = None
        if out is not None:
            out_dir = out if len(inputs) == 1 else out / runner.default_output_dir(input_path, recipe).name

        if events:
            try:
                runner.run_recipe(
                    recipe,
                    input_path,
                    out_dir,
                    registry=registry,
                    use_cache=not no_cache,
                    events=lambda event: print(json.dumps(event), flush=True),
                )
            except KeyboardInterrupt:
                raise typer.Exit(130) from None
            except Exception:
                failures += 1
            continue

        console.print(f"[bold]{input_path.name}[/bold]  ->  recipe [bold]{recipe.name}[/bold]")
        progress = Progress(
            TextColumn("  {task.description}"),
            BarColumn(bar_width=30),
            TextColumn("{task.fields[state]}"),
            TimeElapsedColumn(),
            console=console,
        )
        tasks: dict[str, int] = {}

        def on_event(event: dict, progress=progress, tasks=tasks) -> None:
            kind = event["type"]
            node = event.get("node")
            if kind == "run_started":
                for name in event["nodes"]:
                    tasks[name] = progress.add_task(name, total=1.0, state="waiting", start=False)
            elif kind == "node_started":
                progress.start_task(tasks[node])
                label = event["op"] + (f" ({event['model']})" if event.get("model") else "")
                progress.update(tasks[node], state=label)
            elif kind == "node_progress":
                progress.update(tasks[node], completed=event["fraction"])
            elif kind == "node_finished":
                progress.update(tasks[node], completed=1.0, state="cached" if event["cached"] else "done")
                progress.stop_task(tasks[node])
            elif kind == "warning":
                progress.console.print(f"  [yellow]{node}: {event['message']}[/yellow]")

        try:
            with progress:
                record = runner.run_recipe(
                    recipe, input_path, out_dir, registry=registry, use_cache=not no_cache, events=on_event
                )
        except KeyboardInterrupt:
            console.print("[yellow]Cancelled. No output files were written.[/yellow]")
            raise typer.Exit(130) from None
        except Cancelled:
            console.print("[yellow]Cancelled. No output files were written.[/yellow]")
            raise typer.Exit(130) from None
        except (recipe_module.RecipeError, RegistryError, BackendError, AudioError) as e:
            console.print(f"[red]{e}[/red]")
            failures += 1
            continue

        for name, entry in record["nodes"].items():
            metrics = entry.get("info", {}).get("metrics")
            if metrics:
                console.print(
                    f"  {name}: residual {metrics['residual_vs_mix_db']:+.1f} dB relative to the mix"
                    + (f", SI-SDR {metrics['si_sdr_db']:.2f} dB" if "si_sdr_db" in metrics else "")
                )
        console.print(
            f"  [green]{len(record['outputs'])} files[/green] in {record['output_dir']} ({record['seconds']:.1f} s)"
        )
    if failures:
        raise typer.Exit(1)


@app.command()
def validate(recipe_path: Path = typer.Argument(..., metavar="RECIPE")) -> None:
    """Check a recipe against the installed models and show the resolved parameters."""
    from captainstems import recipe as recipe_module
    from captainstems import runner
    from captainstems.registry import Registry

    try:
        recipe = _load_recipe(recipe_path)
        plans = runner.plan_recipe(recipe, Registry())
    except recipe_module.RecipeError as e:
        _fail(str(e), 2)
    table = Table(title=f"{recipe.name}: {len(plans)} nodes", title_justify="left")
    for column in ("node", "op", "model", "outputs", "resolved params"):
        table.add_column(column)
    for name, plan in plans.items():
        params = ", ".join(f"{key}={value}" for key, value in plan.params.items() if value is not None)
        table.add_row(name, plan.op, plan.model_id or "", ", ".join(plan.outputs), params)
    console.print(table)


@app.command()
def schema(backends: bool = typer.Option(False, "--backends", help="Include each backend's parameter schema")) -> None:
    """Print the JSON Schema of the recipe format."""
    from captainstems import recipe as recipe_module
    from captainstems.backends import base

    data: dict = {"recipe": recipe_module.json_schema()}
    if backends:
        data["backends"] = {}
        for name in base.BACKENDS:
            try:
                data["backends"][name] = recipe_module.backend_param_schema(base.supported_params(name))
            except Exception as e:
                data["backends"][name] = {"error": str(e)}
    print(json.dumps(data if backends else data["recipe"], indent=2))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Address to listen on; keep it local"),
    port: int = typer.Option(8787, "--port", "-p"),
) -> None:
    """Start the local API (and the UI, once built) for the app."""
    try:
        import uvicorn

        from captainstems.server.app import UI_DIST, create_app
    except ImportError as e:
        _fail(f"The server extras are not installed ({e}). Run: uv sync --inexact --extra server")
    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print("[yellow]Warning: the API has no authentication. Only expose it on a network you trust.[/yellow]")
    console.print(f"CaptainStems API on http://{host}:{port}")
    if UI_DIST.is_dir():
        console.print(f"UI: http://{host}:{port}/")
    else:
        console.print("UI not built. For development: cd app && pnpm i && pnpm dev")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


# Models ---------------------------------------------------------------------------

models_app = typer.Typer(help="Manage the model registry.", no_args_is_help=True)
app.add_typer(models_app, name="models")


def _size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit in ("B", "KB") else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return ""


@models_app.command("list")
def models_list(as_json: bool = typer.Option(False, "--json")) -> None:
    """List installed models and the curated ones that can be fetched."""
    from captainstems.registry import Registry

    registry = Registry()
    rows = registry.catalog()
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    table = Table(title=f"Models in {registry.root}", title_justify="left")
    for column in ("id", "backend", "arch", "stems", "status"):
        table.add_column(column)
    for row in rows:
        if row["installed"]:
            status = "[green]installed[/green]"
        elif row.get("curated"):
            status = f"fetch ({_size(row.get('download_bytes', 0))})"
        else:
            status = "[yellow]incomplete[/yellow]"
        table.add_row(row["id"], row["backend"], row.get("arch", ""), ", ".join(row["stems"]), status)
    console.print(table)
    for model_id, problem in registry.problems.items():
        console.print(f"[yellow]{model_id}: broken manifest: {problem}[/yellow]")


@models_app.command("fetch")
def models_fetch(
    ids: list[str] = typer.Argument(..., metavar="ID...", help="Curated model ids, or 'all'"),
    force: bool = typer.Option(False, "--force", help="Download again even if the files are present"),
) -> None:
    """Download curated models and verify their checksums."""
    from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TransferSpeedColumn

    from captainstems.registry import Registry, RegistryError, load_curated

    registry = Registry()
    if ids == ["all"]:
        ids = list(load_curated())
    for model_id in ids:
        console.print(f"[bold]{model_id}[/bold]")
        with Progress(
            TextColumn("  {task.description}"),
            BarColumn(bar_width=30),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=console,
        ) as progress:
            tasks: dict[str, int] = {}

            def on_progress(name: str, done: int, total: int | None, progress=progress, tasks=tasks) -> None:
                if name not in tasks:
                    tasks[name] = progress.add_task(name, total=total)
                progress.update(tasks[name], completed=done, total=total)

            try:
                model = registry.fetch(model_id, progress=on_progress, force=force)
            except (RegistryError, OSError) as e:
                _fail(f"  {e}")
        console.print(f"  [green]verified[/green], installed in {model.folder}")


@models_app.command("add")
def models_add(
    model_id: str = typer.Argument(..., metavar="ID", help="Registry id (also the folder name)"),
    backend: str = typer.Option(..., "--backend", "-b", help="msst, demucs or onnx"),
    weights: list[Path] = typer.Option(..., "--weights", "-w", help="Checkpoint file; repeat for a Demucs bag"),
    stems: str = typer.Option(..., "--stems", "-s", help="Comma separated stems in the model's output order"),
    arch: str = typer.Option(
        "", "--arch", "-a", help="Architecture; for MSST its --model_type (e.g. mel_band_roformer)"
    ),
    config: Path = typer.Option(None, "--config", "-c", help="Config YAML (MSST) or bag YAML (Demucs)"),
    name: str = typer.Option("", "--name"),
    sample_rate: int = typer.Option(44100, "--sample-rate"),
    default: list[str] = typer.Option([], "--default", "-d", help="Default knob, e.g. -d overlap=4"),
    onnx_param: list[str] = typer.Option([], "--onnx-param", help="MDX-Net parameter, e.g. --onnx-param dim_f=3072"),
    license_text: str = typer.Option("", "--license"),
    notes: str = typer.Option("", "--notes"),
    source: str = typer.Option(None, "--source", help="Where the files came from"),
    unsafe_pickle: bool = typer.Option(False, "--unsafe-pickle", help="Allow a checkpoint that needs pickle"),
    move: bool = typer.Option(False, "--move", help="Move the files into the registry instead of copying"),
) -> None:
    """Register your own model: copies the files into the registry and writes its manifest."""
    from pydantic import ValidationError

    from captainstems.registry import Manifest, Registry, RegistryError

    def pairs(items: list[str], what: str) -> dict:
        result = {}
        for item in items:
            key, sep, value = item.partition("=")
            if not sep:
                _fail(f"{what} must look like name=value, got '{item}'", 2)
            try:
                result[key] = json.loads(value)
            except ValueError:
                result[key] = value
        return result

    files = {path.name: path for path in weights}
    if config is not None:
        files[config.name] = config
    try:
        manifest = Manifest(
            id=model_id,
            name=name or model_id,
            backend=backend,
            arch=arch,
            config=config.name if config else None,
            weights=weights[0].name if len(weights) == 1 else [path.name for path in weights],
            stems=[stem.strip() for stem in stems.split(",") if stem.strip()],
            sample_rate=sample_rate,
            defaults=pairs(default, "--default"),
            onnx_params=pairs(onnx_param, "--onnx-param") or None,
            license=license_text,
            notes=notes,
            source=source,
            unsafe_pickle=unsafe_pickle,
        )
        model = Registry().add(manifest, files, move=move)
    except ValidationError as e:
        _fail("; ".join(f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in e.errors()), 2)
    except RegistryError as e:
        _fail(str(e))
    console.print(f"[green]Added[/green] {model.id} in {model.folder}")


@models_app.command("remove")
def models_remove(
    model_id: str = typer.Argument(..., metavar="ID"), yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask")
) -> None:
    """Delete a model and its files from the registry."""
    from captainstems.registry import Registry, RegistryError

    registry = Registry()
    if not yes:
        typer.confirm(f"Delete {registry.root / model_id}?", abort=True)
    try:
        registry.remove(model_id)
    except RegistryError as e:
        _fail(str(e))
    console.print(f"Removed {model_id}")


@models_app.command("verify")
def models_verify(ids: list[str] = typer.Argument(None, metavar="[ID...]")) -> None:
    """Check installed models against the checksums in their manifests."""
    from captainstems.registry import Registry, RegistryError

    registry = Registry()
    failed = False
    for model in registry.list():
        if ids and model.id not in ids:
            continue
        try:
            (model.folder / ".verified.json").unlink(missing_ok=True)
            model.verify()
            console.print(f"[green]ok[/green]    {model.id}")
        except RegistryError as e:
            failed = True
            console.print(f"[red]FAILED[/red] {model.id}: {e}")
    if failed:
        raise typer.Exit(1)


# Cache ----------------------------------------------------------------------------

cache_app = typer.Typer(help="Inspect or clear cached intermediate stems.", no_args_is_help=True)
app.add_typer(cache_app, name="cache")


@cache_app.command("info")
def cache_info() -> None:
    """Show where the cache is and how big it has grown."""
    from captainstems.runner import Cache

    cache = Cache()
    console.print(f"{cache.root}: {_size(cache.size())}")


@cache_app.command("clear")
def cache_clear() -> None:
    """Delete all cached intermediate stems."""
    from captainstems.runner import Cache

    console.print(f"Freed {_size(Cache().clear())}")


if __name__ == "__main__":
    app()
