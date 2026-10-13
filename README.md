# CaptainStems

A power-user stem separation workbench. Run any separation model you choose, including checkpoints you
add yourself, with every inference knob exposed. Compose separations as a graph (a *recipe*) of
separate, subtract, ensemble, post-process, analyze and export steps, and rerun the same recipe on any file.

This is version 2, a rewrite around a recipe engine. The original PyQt application is kept in
[`archive/v1/`](archive/v1/). Plan and decisions:
[CaptainStems v2 handoff](https://claude.ai/artifact/FoargYKnKDffjnQYnFNWzF).

| Part | Where | What |
| --- | --- | --- |
| Engine and CLI | `captainstems/` | Recipes, runner, cache, model registry, backends |
| API server | `captainstems/server/` | FastAPI and WebSocket, local only |
| UI | `app/` | React: recipe graph, run queue, results |

## Setup

Requires [uv](https://docs.astral.sh/uv/), git, and for the UI [pnpm](https://pnpm.io/).

```
git clone --recurse-submodules https://github.com/mikeallisonJS/CaptainStems
cd CaptainStems
uv sync --extra dev --extra server
uv run captainstems bootstrap
uv run captainstems doctor
```

`bootstrap` installs the build of PyTorch that matches your GPU, the model libraries and one build of
onnxruntime. They are deliberately not regular dependencies, because the right build depends on the
machine. `uv sync` therefore removes them again: rerun `bootstrap` afterwards, or use `uv sync --inexact`.
`doctor` shows what was detected and the exact commands `bootstrap` runs; `doctor --set-flavor cpu`
overrides the choice. On Windows the ROCm wheels come from AMD and are compiled per GPU target;
`doctor` shows the detected target, and `doctor --set-rocm-target gfx1151` sets it for a GPU that is
not recognised.

| OS | GPU | PyTorch backends (MSST, Demucs) | ONNX backend |
| --- | --- | --- | --- |
| Windows, Linux | NVIDIA | CUDA | CUDA |
| macOS | Apple Silicon | MPS (fp32) | CoreML |
| Linux | AMD | ROCm | CPU |
| Windows | AMD RX 7000, RX 9000, Ryzen AI 300, Ryzen AI Max | ROCm (AMD's wheels) | DirectML |
| Windows | other AMD, Intel | CPU | DirectML |
| any | none | CPU | CPU |

Tested so far: Windows with an NVIDIA GPU, and Windows with a Radeon 8060S (Ryzen AI Max, ROCm).

## Quick start

```
uv run captainstems models fetch htdemucs
uv run captainstems run recipes/four-stems.yaml song.flac
```

The stems and a `run.json` land in `song [four-stems]/` next to the input. Use `--out` to choose the
folder, and give several files to process them one after another.

## Recipes

A recipe is a YAML file: named nodes, each with an `op`. Nodes read the outputs of other nodes as
`node.stem`; `mix` is the input file.

```yaml
version: 1
name: vocals-instrumental
nodes:
  vox:
    op: separate
    model: mel-band-roformer-vocals-kim
    targets: [vocals]
    params: {overlap: 4, shifts: 2}
  inst:
    op: subtract                     # sample-exact: vocals + instrumental = mix
    inputs: {a: mix, b: vox.vocals}
  check:
    op: analyze                      # how much did the chain lose?
    inputs: {stems: [vox.vocals, inst.out]}
  out:
    op: export
    inputs: {vocals: vox.vocals, instrumental: inst.out}
    params: {format: flac, bit_depth: 24}
```

| Op | Does | Outputs | Parameters |
| --- | --- | --- | --- |
| `separate` | Runs one model on one input | the stems in `targets` (all of the model's by default) | the knobs of the model's backend |
| `subtract` | `a - b`, sample-exact | `out` | `gain_b` |
| `ensemble` | Combines several versions of a stem | `out` | `method` (avg, median, max_spec, min_spec), `weights` |
| `postprocess` | Runs a single-purpose model (dereverb, denoise) | `out` | the knobs of the model's backend |
| `analyze` | `residual = mix - sum(stems)`, levels, optional SI-SDR against a reference file | `residual` | `reference` |
| `export` | Writes files | none | `format` (flac, wav, mp3), `bit_depth`, `sample_rate`, `naming`, `bitrate` |

`defaults:` at the top of a recipe applies to every separate and postprocess node. A knob of the same name
can mean different things per backend (`overlap` is a count of chunks for MSST and a fraction for Demucs
and ONNX); a default is applied to the nodes it fits.

`captainstems validate recipe.yaml` checks a recipe against the installed models and prints every node's
fully resolved parameters. `captainstems schema --backends` prints the JSON Schema of the format and of
each backend's knobs. Examples are in [`recipes/`](recipes/), including the worked example from the handoff.

### Reproducibility

Every run writes `run.json` beside its outputs: the recipe, the resolved parameters of each node, the
SHA-256 of the input and of every model file, and the backend versions. `captainstems run run.json song.flac`
repeats a run with exactly those parameters.

Intermediate stems are cached under `~/.captainstems/cache`, keyed by a node's parameters, its model's
hash and its inputs, so rerunning a recipe only recomputes what changed (`captainstems cache info|clear`).
A run that is cancelled or fails writes no output files.

## Models

Models live in `~/.captainstems/models/`, one folder per model with a `manifest.json`, its config and its
weights. Set `CAPTAINSTEMS_HOME` to move everything CaptainStems stores.

```
uv run captainstems models list
uv run captainstems models fetch mel-band-roformer-vocals-kim scnet-large
uv run captainstems models verify
```

`fetch` downloads curated models from their publishers and verifies them by SHA-256. Weights are never
part of this repository and carry their own licenses, shown in `models list --json` and in the UI.

| Backend | Runs | Knobs |
| --- | --- | --- |
| `msst` | Anything [Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training) builds from a config and a checkpoint: bs_roformer, mel_band_roformer, mdx23c, scnet, htdemucs and more | chunk_size, overlap, batch_size, shifts, tta, dtype, normalize, device |
| `demucs` | Native Demucs `.th` bags | shifts, overlap, segment, split, seed, device |
| `onnx` | UVR's MDX-Net models | overlap, batch_size, denoise, compensate, device |

### Adding your own model

```
uv run captainstems models add my-vocals --backend msst --arch mel_band_roformer \
    --config path/to/config.yaml --weights path/to/model.ckpt --stems vocals -d overlap=4
```

This copies the files into the registry and writes the manifest. For MSST, `--arch` is its `--model_type`
and `--stems` are the model's outputs (its `target_instrument`, or all `instruments` if it has none). For
Demucs give the bag's `.yaml` as `--config` and its `.th` files as `--weights`. ONNX models carry no config,
so they need `--onnx-param dim_f=3072 --onnx-param dim_t=256 --onnx-param n_fft=6144`.

Checkpoints are loaded without Python's pickle by default. If a checkpoint needs it and you trust its
source, add `--unsafe-pickle`.

## UI

```
uv run captainstems serve          # API on http://127.0.0.1:8787
cd app && pnpm i && pnpm dev       # UI with hot reload on http://localhost:5173
```

or as a desktop app, which starts the server itself:

```
cd app && pnpm i && pnpm build && pnpm desktop
```

or build the UI once (`cd app && pnpm i && pnpm build`) and open http://127.0.0.1:8787/, where the
server then serves it.

- **Recipe**: the recipe as a graph. Add nodes from the toolbar, connect them by dragging from a stem to
  an input, and edit the selected node in the panel. The panel is generated from the JSON Schema, so it
  always shows exactly the knobs the chosen model's backend honors. Load, save and edit recipes as YAML.
- **Run**: pick input files (browse, paste a path, or drop them), then watch every node's progress, the
  log and any warnings. Runs can be cancelled.
- **Results**: waveform and spectrogram of every stem, the mix and the residual. One transport plays them;
  A/B switches between any two without losing the position (Space plays, X switches).
- **Models**: what the machine can run, fetch curated models, add your own. The Doctor part overrides the
  detected torch flavor (and the ROCm target on Windows), like `doctor --set-flavor`; the desktop app can then
  reinstall the model libraries from there, a browser shows the `bootstrap` command to run.

The server listens on the local machine only and has no authentication. The desktop app (`app/src/main/`)
spawns it on a free port, offers to run `bootstrap` on the first start and stops it on exit. `cd app && pnpm dist`
builds the installer (NSIS, AppImage or dmg): the installed app creates its own Python environment with uv on
the first start, so the installer stays small and one build serves every GPU. Pushing a `v*` tag builds all
three on GitHub Actions.

## Development

```
uv run pytest                    # all tests; those needing models fetch them on first use
uv run pytest -m "not models"    # without torch or model weights
uv run ruff check . && uv run ruff format .
cd app && pnpm test && pnpm typecheck
```

`CLAUDE.md` has the rules of the codebase. MSST is a pinned submodule at `third_party/msst`; it is wrapped,
never modified.

## License

MIT, see [LICENSE](LICENSE). Model weights are downloaded separately and carry their own licenses.
