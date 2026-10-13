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
API URL, the real path of dropped files and a `bootstrap()` call
(`window.captainstems`): the Doctor part of the Models view uses it after a
flavor change to reinstall the model libraries, which the shell runs with the
loading screen showing, then restarts the server on the same port and reloads
the UI.

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

### Windows code signing

Optional, and switched on by secrets alone. The release workflow signs with
Azure Artifact Signing (formerly Trusted Signing) through electron-builder,
using the same six repository secrets as Cadent's installer workflow, so the
signing account, app registration and certificate profile set up there serve
this app too:

    AZURE_SIGN_TENANT_ID      the Entra tenant holding the signing identity
    AZURE_SIGN_CLIENT_ID      app registration with the Code Signing Certificate Profile Signer role
    AZURE_SIGN_CLIENT_SECRET  its client secret
    AZURE_SIGN_ENDPOINT       regional URI, e.g. https://eus.codesigning.azure.net/
    AZURE_SIGN_ACCOUNT        Artifact Signing account name
    AZURE_SIGN_PROFILE        certificate profile name within that account

None set: an unsigned build that runs, with a SmartScreen warning on first
launch. All six: every `.exe` in the app and the installer are signed and
timestamped, and the workflow verifies the installer's signature. A partial set
fails the build. `electron-builder.cjs` holds the rule; to sign a local build,
export the three `AZURE_*` variables and the three `CAPTAINSTEMS_SIGN_*` ones it
documents, on a machine with PowerShell (the TrustedSigning module is installed
on first use).

### Auto-update

The installed app checks an update feed after the window opens and every
four hours, downloads a newer version in the background and asks before
restarting; "Later" installs it on the next quit. The Models view shows the
app's version and a manual check. Nothing is checked from a checkout.

The feed is a folder of files electron-builder writes beside the installers:
`latest.yml` (`latest-linux.yml`, `latest-mac.yml`) naming the newest version,
the installers and their `.blockmap` files for differential downloads.
`electron-builder.cjs` bakes the folder's URL into the app
(`CAPTAINSTEMS_UPDATE_URL`, default `https://downloads.mikeallisonjs.com/captainstems`),
and the release workflow uploads the files there on a `v*` tag: Cloudflare R2
behind that custom domain, using the same five `R2_*` secrets as Cadent. The
repository is private, so GitHub releases cannot serve the feed. Installers
are written once per version; only `latest*.yml` is overwritten.

macOS: updates need a signed and notarized app, which is not set up, so the
check reports an error there until it is. Windows updates are verified
against the running app's signature once signing is configured.

Not done yet: macOS signing and notarization, an app icon.
