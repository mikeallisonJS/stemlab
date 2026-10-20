# Changelog

Curated per-release notes. Entries accumulate as fragments in `changelog.d/`
and are rendered here by the release PR (see the README under Releases).

<!-- towncrier release notes start -->

## v1.0.0 — 2026-10-17

### Features

- Stemlab 1.0: a stem separation workbench. Run any open separation model (Demucs, the Mel-Band RoFormer, SCNet and BS-RoFormer families, or your own checkpoints) with every parameter exposed, compose separate, subtract, ensemble, post-process, analyze and export steps into recipes, queue whole folders, and get a `run.json` with every result so it can be reproduced. GPU acceleration on NVIDIA and AMD with a processor fallback. The desktop app installs its own runtime on first start and updates itself.

### Fixes

- The desktop app reopens the recipe you were editing instead of starting from the example on every launch. ([#9](https://github.com/mikeallisonJS/Stemlab/issues/9))
- Quitting while the window is open, for example to install an update, no longer stops on a "The server stopped" error.
