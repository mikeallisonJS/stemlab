# Stemlab

A power-user stem separation workbench. Run any separation model you choose, including checkpoints you
add yourself, with every inference knob exposed. Compose separations as a graph (a *recipe*) of
separate, subtract, ensemble, post-process, analyze and export steps, and rerun the same recipe on any file.

The first release is 1.0. The code is a rewrite around a recipe engine of an earlier PyQt application
that was never released; it is kept in [`archive/v1/`](archive/v1/). Plan and decisions:
[Stemlab v2 handoff](https://claude.ai/artifact/FoargYKnKDffjnQYnFNWzF).

Stemlab was called CaptainStems before its first release. The package, the CLI (`stemlab`), the
environment variables (`STEMLAB_*`) and the data folder (`~/.stemlab`) all carry the new name; an existing
`~/.captainstems` is renamed to `~/.stemlab` on first start, so downloaded models are kept.

| Part | Where | What |
| --- | --- | --- |
| Engine and CLI | `stemlab/` | Recipes, runner, cache, model registry, backends |
| API server | `stemlab/server/` | FastAPI and WebSocket, local only |
| UI | `app/` | React: recipe graph, run queue, results |
| Desktop shell | `app/src/main/` | Electron: starts the server, first-run setup, auto-update |

## Setup

Requires [uv](https://docs.astral.sh/uv/), git, and for the UI [pnpm](https://pnpm.io/).

```
git clone --recurse-submodules https://github.com/mikeallisonJS/Stemlab
cd Stemlab
uv sync --extra dev --extra server
uv run stemlab bootstrap
uv run stemlab doctor
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
uv run stemlab models fetch htdemucs
uv run stemlab run recipes/four-stems.yaml song.flac
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

`stemlab validate recipe.yaml` checks a recipe against the installed models and prints every node's
fully resolved parameters. `stemlab schema --backends` prints the JSON Schema of the format and of
each backend's knobs. Examples are in [`recipes/`](recipes/), including the worked example from the handoff.

### Reproducibility

Every run writes `run.json` beside its outputs: the recipe, the resolved parameters of each node, the
SHA-256 of the input and of every model file, and the backend versions. `stemlab run run.json song.flac`
repeats a run with exactly those parameters.

Intermediate stems are cached under `~/.stemlab/cache`, keyed by a node's parameters, its model's
hash and its inputs, so rerunning a recipe only recomputes what changed (`stemlab cache info|clear`).
A run that is cancelled or fails writes no output files.

## Models

Models live in `~/.stemlab/models/`, one folder per model with a `manifest.json`, its config and its
weights. Set `STEMLAB_HOME` to move everything Stemlab stores.

```
uv run stemlab models list
uv run stemlab models fetch mel-band-roformer-deux scnet-xl-ihf
uv run stemlab models verify
```

The curated list (`stemlab models list`) holds, as of October 2026: becruily's Mel-Band RoFormer Deux
(vocals and instrumental in one pass, the best all-rounder), unwa's BS-RoFormer Resurrection (vocal and
instrumental variants), Kim's and viperx's older vocal models, SCNet XL IHF and HT Demucs for 4 and 6 stems,
and single-purpose models for dereverb, denoise and karaoke (lead against backing vocals). The
`vocals-ensemble` recipe averages three vocal models, which is how the leaderboard results are made.
Some weights are non-commercial (Deux is CC-BY-NC-4.0) and several community checkpoints state no licence;
each manifest records what its publisher says.

The lists (`models list`, the Models view) show each model's SDR as published by its authors. The benchmarks
differ (MUSDB18, MVSEP's multisong set, a publisher's own recordings), so compare numbers within one only.

`fetch` downloads curated models from their publishers and verifies them by SHA-256. Weights are never
part of this repository and carry their own licenses, shown in `models list --json` and in the UI.

| Backend | Runs | Knobs |
| --- | --- | --- |
| `msst` | Anything [Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training) builds from a config and a checkpoint: bs_roformer, mel_band_roformer, mdx23c, scnet, htdemucs and more | chunk_size, overlap, batch_size, shifts, tta, dtype, normalize, device |
| `demucs` | Native Demucs `.th` bags | shifts, overlap, segment, split, seed, device |
| `onnx` | UVR's MDX-Net models | overlap, batch_size, denoise, compensate, device |

### Adding your own model

```
uv run stemlab models add my-vocals --backend msst --arch mel_band_roformer \
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
uv run stemlab serve          # API on http://127.0.0.1:8787
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
spawns it on a free port, offers to run `bootstrap` on the first start and stops it on exit.

## Building the installer

Needs everything from Setup plus Node 24 and pnpm 11, the MSST submodule checked out
(`git submodule update --init`), and FFmpeg on the `PATH` (or named in `FFMPEG`) to bundle it.

```
cd app
pnpm i
pnpm dist
```

`pnpm dist` builds the UI and the Electron shell, then `scripts/prepare-engine.mjs` assembles
`app/build/engine`: the engine as a wheel (`uv build`), `recipes/`, the MSST submodule, the built UI and
FFmpeg. electron-builder packs that beside the shell and writes the installer for the current OS to
`app/release/`:

| OS | Installer |
| --- | --- |
| Windows | `Stemlab-Setup-<version>.exe` (NSIS) |
| Linux | `Stemlab-<version>.AppImage` |
| macOS | `Stemlab-<version>.dmg`, plus a `.zip` for auto-update |

No Python, torch or model ships in the installer. On its first start the installed app downloads a pinned
uv, creates its own Python environment in the user data folder, installs the bundled wheel and then offers
`bootstrap` for the GPU libraries, so the installer stays small and one build serves every GPU.

A local build is unsigned unless the six Azure Artifact Signing variables are set; macOS builds are not
signed or notarized yet. Signing, the auto-update feed and the variables that point a checkout at a
packaged-style setup are described in [`app/src/main/README.md`](app/src/main/README.md).

## Development

```
uv run pytest                    # all tests; those needing models fetch them on first use
uv run pytest -m "not models"    # without torch or model weights
uv run ruff check . && uv run ruff format .
cd app && pnpm test && pnpm typecheck
```

`CLAUDE.md` has the rules of the codebase. MSST is a pinned submodule at `third_party/msst`; it is wrapped,
never modified.

## Releases

Changeset-style, the same flow as Cadent: each PR declares its release intent as a fragment, a
bot-maintained release PR aggregates them, merging that PR ships. Versions are never bumped and `v*` tags
are never pushed by hand. The version in the tree is `1.0.0.dev0`, so the first release PR is `v1.0.0`.

1. A PR that touches `stemlab/`, the app, `recipes/`, `third_party/` or `pyproject.toml` adds one file
   `changelog.d/<issue>.<type>.md` (or `+<slug>.<type>.md` without an issue). `changelog-check` fails the
   PR without one. Types `breaking`, `feature` and `bugfix` render into `CHANGELOG.md` and decide the bump
   (`breaking` is major, `feature` minor, `bugfix` patch); `chore` and `docs` never render and only ever
   mean a patch. A `.devN` version releases as its base version whatever the fragments say. The body is
   one or two sentences in a user-facing voice.
2. Every push to `main` runs `release-pr.yml`: it computes the next version, writes it to
   `pyproject.toml`, `stemlab/__init__.py`, `app/package.json` and `uv.lock`, renders the fragments into
   `CHANGELOG.md` with towncrier, and keeps a `release/next` PR up to date with all of it.
3. Merging the release PR is the release decision. `tag-release.yml` tags the merge commit `vX.Y.Z`,
   drafts the GitHub Release with the changelog section as its body, and dispatches `release.yml` at the
   tag, which builds and signs the installers, publishes the update feed to R2 and attaches the files to
   the draft. Publishing the draft is the last human step.

`uv run --with towncrier python scripts/release.py next-version` shows what the pending fragments add
up to.

The release build needs repository secrets, shared with Cadent:

| Secrets | Needed for | Without them |
| --- | --- | --- |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_HOST` | Uploading the auto-update feed to Cloudflare R2 under `stemlab/` | The tag build fails |
| `AZURE_SIGN_TENANT_ID`, `AZURE_SIGN_CLIENT_ID`, `AZURE_SIGN_CLIENT_SECRET`, `AZURE_SIGN_ENDPOINT`, `AZURE_SIGN_ACCOUNT`, `AZURE_SIGN_PROFILE` | Signing the Windows build | Unsigned Windows build (SmartScreen warns); a partial set fails |

## Support

Stemlab is free and MIT licensed. If it saves you time, you can support the work on
[GitHub Sponsors](https://github.com/sponsors/mikeallisonJS) or [donate directly](https://captainssounds.com/donate).

## License

MIT, see [LICENSE](LICENSE). Model weights are downloaded separately and carry their own licenses.
