# CaptainStems - Technical Context

## Technology Stack

### Core Technologies

- **Python**: Primary programming language (3.10.x recommended)
- **PyQt6**: Cross-platform GUI framework, including Qt Multimedia for playback
- **FFmpeg**: Audio decoding and format conversion (system installation or the imageio-ffmpeg binary)

### AI Models

Each backend lives in its own virtual environment:

| Backend   | Package                          | Framework                 | Models                                    |
| --------- | -------------------------------- | ------------------------- | ----------------------------------------- |
| demucs    | demucs 4.1.0                     | PyTorch (CUDA/MPS/CPU)    | v4: htdemucs, htdemucs_ft, htdemucs_6s; v3: hdemucs_mmi, mdx, mdx_extra |
| spleeter  | spleeter 2.4.2                   | TensorFlow 2.12           | 2stems, 4stems, 5stems                    |
| bandsplit | audio-separator 0.47.0           | PyTorch (CUDA/MPS/CPU)    | BS-RoFormer vocals, BS-RoFormer SW 6 stems |
| d3net     | nnabla 1.39.0 + onnxruntime 1.18 | ONNX Runtime (DirectML/CPU) | Sony's pretrained D3Net (standard, fast)  |

### Audio Libraries

- **soundfile**: Reading audio for the waveform display and inside the runner scripts
- **NumPy**: Waveform envelopes

The application itself does not import PyTorch, TensorFlow, librosa or matplotlib.

### Development Tools

- **pip / venv**: Package and environment management (uv is used as a fallback to obtain a suitable Python)
- **pytest, pytest-qt**: Test suite

## Development Setup

### Recommended Environment

- Python 3.10.x virtual environment
- `pip install -r requirements-dev.txt`
- IDE with Python support (VS Code, PyCharm, etc.)

### Environment Setup Scripts

- `start.bat` / `start.sh`: Create the application's virtual environment and launch
- `setup_compatible_env.sh`: Creates a Python 3.10 environment when the default Python is newer
- `start_compatible.sh`: Launches the application with that environment
- `captain.py`: `--setup`, `--check`, `--install-model`, `--uninstall-model`, `--separate`

### Installation Process

The application has a two-layered installation approach:

1. Core dependencies via requirements.txt (small, installed by the launchers)
2. Model backends on demand, each into `<application data>/envs/<backend>`, with weights in
   `<application data>/weights/<backend>`

Application data directory: `%LOCALAPPDATA%\CaptainStems` (Windows),
`~/Library/Application Support/CaptainStems` (macOS), `~/.local/share/CaptainStems` (Linux),
or `CAPTAINSTEMS_HOME`.

## Technical Constraints

### Python Version Compatibility

| Python Version | Compatibility  | Notes                                        |
| -------------- | -------------- | -------------------------------------------- |
| 3.10.x         | ✅ Recommended | Every backend can be installed               |
| 3.9.x          | ⚠️ Limited     | Spleeter and D3Net only                      |
| 3.11.x         | ⚠️ Limited     | Everything except D3Net (NNabla wheels end at 3.10) |
| 3.12.x         | ⚠️ Limited     | Demucs and Band-Split RoFormer only          |

### Platform-Specific Considerations

- **Windows** (tested):

  - Spleeter pins tensorflow-io-gcs-filesystem 0.32.0, which has no Windows build; 0.31.0 is
    installed and Spleeter itself with `--no-deps`
  - D3Net uses onnxruntime-directml for GPU acceleration on any DirectX 12 GPU
  - PyTorch comes from the CUDA 12.6 wheel index when `nvidia-smi` reports a GPU, otherwise the CPU index

- **macOS** (untested):
  - Apple Silicon: tensorflow-macos / tensorflow-metal for Spleeter, PyTorch from PyPI with MPS
  - NNabla has no Apple Silicon wheels, so D3Net is expected not to install there

- **Linux** (untested): same package choices as Windows, without DirectML

### Dependencies Challenges

- **Conflicting pins**: Spleeter (NumPy < 1.24), NNabla (NumPy 1.26, protobuf 3.20) and
  audio-separator (NumPy 2) can not coexist, hence the isolated environments
- **NNabla performance**: single-threaded CPU inference, solved by exporting to ONNX. The export
  must run in one process per network; converting several in one process crashes NNabla
- **D3Net weights**: nnabla.org no longer hosts them. The runner downloads `d3net-mss.h5` from a
  mirror and verifies its SHA-256. These weights match upstream commit `f7e22ae`, not the current
  master (whose reworked blocks need different weights)

## External Dependencies

### FFmpeg

- Used by the application for decoding and exporting
- Backends receive WAV files, so they only need FFmpeg for their own startup checks; the bundled
  binary is put on their PATH when no system FFmpeg exists

### AI Model Weights

- Downloaded automatically during first use (D3Net: during installation)
- Stored below the application data directory, removed when the model is uninstalled
- Sizes: Demucs 80-320 MB per model, BS-RoFormer about 650 MB per model, Spleeter and D3Net under 100 MB

## Technical Roadmap Considerations

- Testing on macOS and Linux
- Packaging the application for users without Python
- Sharing PyTorch between backends
