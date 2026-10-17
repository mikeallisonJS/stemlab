# Privacy Policy for Stemlab

**Last updated: 16 October 2026**

Stemlab is a stem separation workbench that runs entirely on your own
computer. This policy describes what it does with your data. The short
version: your audio and everything made from it never leave your device, and
there is no analytics, telemetry, tracking, or account of any kind.

## What Stemlab does not do

- **No account.** Stemlab has no sign-in, no user profile, and no backend of
  its own; there is no Stemlab server for your data to be sent to.
- **No telemetry or analytics.** Stemlab contains no analytics SDK, crash
  reporter, usage tracker, or error-reporting service.
- **No advertising**, and no sharing or selling of data to anyone.
- **No transmission of your audio.** Separation runs locally, on your machine,
  using models stored on your machine. The files you process, the stems that
  come out, your recipes and your settings are never uploaded.

## What is stored, and where

Everything Stemlab keeps is a plain file in your own user profile. Nothing is
uploaded.

| Where | What it holds |
| --- | --- |
| `~/.stemlab/models/` | The separation models you chose to download. |
| `~/.stemlab/cache/` | Intermediate results, so a rerun of a recipe can skip steps it has already computed. |
| `~/.stemlab/uploads/` | A copy of a file dropped onto the UI when it runs in a browser, which cannot tell the engine where the file lives. The desktop app uses files where they are. |
| `~/.stemlab/outputs/` | The stems and the `run.json` for each run, unless you chose another output folder. |
| `~/.stemlab/config.json` | Your settings. |
| `%APPDATA%\Stemlab\` (Windows) | The desktop app's own data: the Python runtime and engine libraries it installs on first start, and a downloaded update waiting to be installed. |

Each run's `run.json` records the parameters and model checksums the run
used, and the name of the input file, so that the result can be reproduced.
It stays beside the stems.

You can delete any of this at any time by deleting the folder. Uninstalling
Stemlab removes the application and leaves these folders in place, so that a
reinstall picks up where you left off.

## Network connections

Stemlab makes no network connection while separating audio. It connects to
the internet in these situations, and only to download files:

1. **Installing its runtime, on first start.** The desktop app downloads the
   `uv` tool and a Python runtime from GitHub (`github.com`), then the
   engine's libraries from the Python Package Index (`pypi.org`, which serves
   files from `files.pythonhosted.org`). With your confirmation it then
   installs the build of PyTorch that matches your graphics card, from
   `download.pytorch.org` or, for AMD cards on Windows, from AMD's package
   repository (`stable.repo.amd.com`). Progress is shown throughout.
2. **Downloading a separation model**, when you first choose it. Models are
   fetched from the public repositories their authors publish them on:
   Hugging Face (`huggingface.co`), GitHub (`github.com`,
   `raw.githubusercontent.com`) and Meta's public files host
   (`dl.fbaipublicfiles.com`). Stemlab shows the size before it starts and
   verifies the checksum afterwards. Until you choose a model, no download
   happens.
3. **Checking for updates.** The installed desktop app asks
   `downloads.mikeallisonjs.com` for the newest version shortly after it
   opens and every four hours while it is running, downloads a newer version
   in the background, and asks before restarting to install it. This check
   is automatic; it requests one small file and sends nothing about you or
   your use of the app.

All of these only download files to your computer. None of them uploads your
audio, your stems, your recipes, your settings, or any account or
installation identifier.

Like any download, these requests do reveal your IP address and a user-agent
string to the server you are downloading from; that is how the internet works,
and it is the same information your browser sends when you visit a web page.
Stemlab adds nothing to it: no account, no device fingerprint, and no
identifier that would let anyone connect one download to another.

## Children

Stemlab is a general-purpose audio utility and is not directed at children.
It collects no personal information from anyone, in the sense of being
received by us: Stemlab has no backend of its own, and the only servers it
ever contacts are the download hosts named above, which it fetches files from
and sends nothing to. Deleting the folders listed above removes what is
stored locally.

## Changes to this policy

If this policy changes, the updated version will be published at this address
and the date at the top will change.

## Contact

Questions about this policy: <dj.mikeallison@gmail.com>

Stemlab is open source. If you would prefer to verify any of the above rather
than take it on trust, the entire source is at
<https://github.com/mikeallisonJS/Stemlab>.
