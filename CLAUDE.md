# Stemlab

Power-user stem separation workbench. Python engine + CLI (`stemlab/`), FastAPI server (`stemlab/server/`), Electron+React UI (`app/`). The unreleased PyQt predecessor lives in `archive/v1/` and is dead; never import from it. The first release is 1.0; the `v2` branch name is the rewrite's, not the version's.

## Commands
- `uv sync --extra dev --extra server` — install
- `uv run stemlab bootstrap` — install torch for the detected GPU, the model libraries and onnxruntime. `uv sync` removes them again (they are not declared dependencies); rerun bootstrap after it, or use `uv sync --inexact`
- `uv run stemlab doctor` — show detected OS / GPU / torch flavor
- `uv run stemlab run recipes/<name>.yaml <audio>` — run a recipe
- `uv run stemlab serve` — API on :8787 for the UI
- `uv run pytest` — tests; `uv run ruff check .` — lint
- `cd app && pnpm i && pnpm dev` — UI against a running server
- `cd app && pnpm build && pnpm desktop` — the Electron app; it starts the server itself (`app/src/main/`)
- `cd app && pnpm dist` — the installer; the installed app makes its own Python env with uv on first start

## Rules
- Backends implement `stemlab/backends/base.py`; never call a backend from the UI or server directly, always through the runner.
- All knobs are declared in the backend's `supported_params`; the UI form is generated from the recipe JSON Schema, never hand-built.
- Model weights never enter git. Registry root is `~/.stemlab/models/`.
- Torch is never a declared dependency of the package; the bootstrap installs the right flavor. Tests must pass on CPU.
- MSST is a pinned submodule at `third_party/msst`; wrap, don't modify.
- Every run writes `run.json` with resolved params and model sha256s. If a result can't be reproduced from `run.json`, that's a bug.
- A PR that touches code adds a changelog fragment, `changelog.d/<issue>.<type>.md` or `+<slug>.<type>.md` (README: Releases). Releases are cut by merging the bot's `release/next` PR; never bump versions or push `v*` tags by hand.
- Plan and decisions: see the handoff doc (link in README).
