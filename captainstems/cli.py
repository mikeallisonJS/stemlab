"""The `captainstems` command line."""

from __future__ import annotations

import json
import sys

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
    set_flavor: str = typer.Option(None, "--set-flavor", help="Override the torch flavor: cuda, rocm, mps, cpu or auto"),
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
    table.add_row("GPU", f"{info.gpu} ({info.vram_mb} MiB)" if info.gpu and info.vram_mb else (info.gpu or "none detected"))
    flavor = info.flavor if info.flavor_source == "detected" else f"{info.flavor} (override; detected {info.detected_flavor})"
    table.add_row("Torch flavor", flavor)

    torch = info.torch
    if torch["version"]:
        runs_on = "CUDA" if torch["cuda"] else ("MPS" if torch["mps"] else "CPU only")
        table.add_row("torch", f"{torch['version']} - {runs_on}")
    else:
        table.add_row("torch", "[yellow]not installed[/yellow]")
    onnx = info.onnxruntime
    if onnx["version"]:
        table.add_row("onnxruntime", f"{onnx['version']} - {', '.join(p.replace('ExecutionProvider', '') for p in onnx['providers'])}")
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


if __name__ == "__main__":
    app()
