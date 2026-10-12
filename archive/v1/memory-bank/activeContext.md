# CaptainStems - Active Context

## Current Focus

The application is feature complete (version 1.0.0). The focus moves from building features to:

1. Testing on macOS and Linux
2. Packaging and distribution
3. Refinements based on real use

## Active Decisions

### One isolated environment per model backend

- The separation libraries pin incompatible NumPy / PyTorch / TensorFlow versions, so they can not
  share an environment (this is why the earlier single-environment approach with
  fix_compatibility.sh kept breaking)
- `core/envs.py` creates a virtual environment per backend below the application data directory
- Models always run as subprocesses; the application environment only has PyQt6, NumPy, soundfile
- Uninstalling is deleting the environment folder; nothing else is affected

### Model lineup

- **Demucs**: package 4.1.0 provides both v4 (htdemucs, htdemucs_ft, htdemucs_6s) and v3
  (hdemucs_mmi, mdx, mdx_extra). The model names demucs/demucs_extra/tasnet from earlier notes are
  v2 models that no current Demucs release can load
- **Band-Split**: Band-Split RNN has no pip package and no usable public pretrained weights. Its
  successor Band-Split RoFormer is used instead, through python-audio-separator
- **D3Net**: Sony's NNabla implementation is single-threaded on the CPU (minutes per second of
  audio). The pretrained networks are converted to ONNX at install time and run with ONNX Runtime
  (DirectML on Windows)
- **Spleeter**: 2.4.2 with TensorFlow 2.12, driven through its Python API by a runner script

### Python Version Strategy

- Primary target is Python 3.10.x: the only version every backend supports
- Each model declares its supported versions; another interpreter or uv is used when needed

### User Experience Priorities

- Focus on simplicity and intuitive interaction
- Drag-and-drop functionality as primary input method
- Clear visual feedback during processing (status text, real progress, cancel)
- Interactive audio playback for results

## Recent Changes

- Rebuilt model handling around isolated environments and a shared processing pipeline
- Replaced the non-existent `band-split-rnn` and `d3net` packages with working backends
- Added the file queue (batch processing), settings, themes, export formats and the command line mode
- Replaced the matplotlib/librosa waveform display with a lightweight custom widget
- Added Windows support (start.bat, no POSIX-only calls)
- Added the test suite

## Next Steps

### Short-term

- Verify macOS (Apple Silicon) and Linux
- Add the LICENSE file

### Medium-term

- Packaged installers so users do not need Python
- Synchronized multi-stem playback with mute/solo

### Long-term

- Share PyTorch between backends to reduce disk usage
- Additional models from python-audio-separator's catalog (MDX-Net, Mel-Band RoFormer)

## Open Questions

- How to distribute: PyInstaller bundle that still creates model environments, or a bootstrapper
  that installs Python 3.10 itself (for example with uv)?
- Should finished results of large batches be discarded once they were saved automatically?
