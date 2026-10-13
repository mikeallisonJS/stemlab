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

Environment variables, all optional:

    CAPTAINSTEMS_API      use a server that is already running; nothing is spawned
    CAPTAINSTEMS_PYTHON   the interpreter to run the server with (default: <repo>/.venv, else uv)
    ELECTRON_RENDERER_URL load the UI from this URL instead of Vite or the built files

Not done yet: a managed Python environment for the packaged app (today the
shell needs the repository's `.venv` or `uv` on the PATH) and the
electron-builder installers.
