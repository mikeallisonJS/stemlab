# CaptainStems - Progress Tracker

## Project Status: Feature Complete (1.0.0)

All components planned in the project brief are implemented. Verified end to end on Windows 11
(Python 3.10, NVIDIA GPU). macOS and Linux code paths exist but have not been run yet.

## Completed Components

### Project Setup

- [x] Repository initialized
- [x] README.md created with documentation
- [x] PROJECT.md created with detailed specifications
- [x] .gitignore configured for Python projects
- [x] PyQt6 selected as UI framework
- [x] Memory bank initialized
- [ ] LICENSE file (README states MIT, the file itself is still missing)

### Environment Management

- [x] requirements.txt with the application's own dependencies
- [x] Isolated environment per model backend (`core/envs.py`)
- [x] start.bat (Windows), start.sh and setup_compatible_env.sh / start_compatible.sh (macOS/Linux)
- [x] Fallback to another Python installation or uv when a model does not support the running Python

### Installation Components

- [x] captain.py unified entrypoint (launch, --setup, --check, --install-model, --uninstall-model, --separate)
- [x] run.py launcher with dependency checks
- [x] install_demucs.py, install_spleeter.py, install_bandsplit.py, install_d3net.py
- [x] In-application installation with live installer output and cancel
- [x] Uninstallation (deletes the model's environment and weights)

### UI Development

- [x] Main window implementation
- [x] Audio drop area with drag-and-drop support (files and folders, click to browse)
- [x] Model selection interface (default models, advanced selection, manage models)
- [x] Processing progress display with status text and cancel

### Audio Processing

- [x] Audio file validation (files are probed when added)
- [x] Audio format conversion with FFmpeg (bundled fallback)
- [x] Demucs v4 integration
- [x] Processing pipeline implementation (`core/pipeline.py`)

### Results Interface

- [x] Results window implementation
- [x] Waveform visualization
- [x] Audio playback controls (shared position across stems, original mix for comparison, volume)
- [x] Stem export functionality (WAV, FLAC, AIFF, MP3, M4A, OGG)

### Advanced Features

- [x] Additional model support (Demucs v3, Spleeter, Band-Split RoFormer, D3Net)
- [x] Batch processing (file queue)
- [x] Settings interface
- [x] User preferences persistence (QSettings)
- [x] Light and dark theme
- [x] Command line separation

### Quality

- [x] Unit tests for core services, models and user interface (`python -m pytest`)
- [x] Integration tests running every real model (`CAPTAINSTEMS_INTEGRATION=1`)

## Known Issues

- macOS and Linux have not been tested. Apple Silicon specifics (tensorflow-macos, MPS) follow the
  libraries' documentation but are unverified
- D3Net and Band-Split RoFormer are slow without a GPU
- Model environments are large (Demucs and Band-Split RoFormer each bring their own PyTorch)
- D3Net's pretrained weights are no longer hosted by Sony; they are downloaded from a mirror and
  verified against a pinned SHA-256 checksum
- Results of a session are kept in the temporary directory until the application closes, which
  can use a lot of disk space for very large batches

## Success Metrics

- [x] Application can load and validate audio files
- [x] At least one AI model successfully integrated (all five families work)
- [x] Audio separation works end-to-end
- [x] Results can be played back and exported

## Possible Next Steps

1. Test and fix on macOS (Apple Silicon) and Linux
2. Packaged installers (PyInstaller / Briefcase)
3. Synchronized multi-stem playback with mute/solo
4. Sharing one PyTorch installation between Demucs and Band-Split RoFormer to save disk space
