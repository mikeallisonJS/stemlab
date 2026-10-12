# Electron main process

Reserved for phase 4 of the handoff: spawn the API server, bootstrap the Python
environment with uv on first run, detect the GPU and show the Doctor screen.

Until then the UI runs in a browser:

    uv run captainstems serve      # API on :8787, also serves app/dist when built
    cd app && pnpm i && pnpm dev   # UI with hot reload on :5173
