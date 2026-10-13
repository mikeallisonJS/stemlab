# Electron main process

The desktop shell. `main.ts` starts `python -m captainstems serve` on a free
port, streams its output to a loading screen, waits until `/system` answers,
then opens the UI. On the first run, when `/system` reports no torch, it offers
to run `captainstems bootstrap` (torch for the detected GPU, the model
libraries, onnxruntime) and restarts the server afterwards. The server is killed
when the window closes.

    cd app && pnpm i && pnpm build   # the UI the server hosts
    pnpm desktop                     # bundle src/main with esbuild, start Electron

With `pnpm dev` running, the shell loads the Vite dev server instead of the
built UI, so renderer changes hot-reload. `preload.ts` hands the renderer the
API URL and the real path of dropped files (`window.captainstems`).

## The packaged app

    pnpm dist      # build the UI and the shell, assemble build/engine, run electron-builder

`scripts/prepare-engine.mjs` assembles `build/engine`: the engine as a wheel
(`uv build`), `recipes/`, the MSST submodule, the built UI and FFmpeg when one
is on the PATH (or named in `FFMPEG`). electron-builder ships that folder as
`resources/engine` next to the shell, and makes an NSIS installer on Windows,
an AppImage on Linux and a dmg on macOS (`release/`). The release workflow
(`.github/workflows/release.yml`) does this for all three on a `v*` tag.

On its first start the packaged app (`python.ts`) downloads a pinned uv,
creates a Python environment under the user data folder (uv-managed CPython,
everything uv downloads stays in that folder), installs the bundled wheel and
starts the server with `CAPTAINSTEMS_ROOT` pointing at the engine folder. Then
the usual first-run prompt offers `bootstrap` for the GPU libraries. A newer
wheel (a different sha256) is reinstalled on the next start.

Environment variables, all optional:

    CAPTAINSTEMS_API      use a server that is already running; nothing is spawned
    CAPTAINSTEMS_PYTHON   the interpreter to run the server with (default: <repo>/.venv, else uv)
    ELECTRON_RENDERER_URL load the UI from this URL instead of Vite or the built files
    CAPTAINSTEMS_MANAGED  =1: behave like the packaged app from a checkout, with
    CAPTAINSTEMS_ENGINE   the engine folder to use (default: resources/engine) and
    CAPTAINSTEMS_DATA     the user data folder to use

Not done yet: code signing, and auto-update.
