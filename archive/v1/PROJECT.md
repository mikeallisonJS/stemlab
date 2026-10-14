# CaptainStems - Audio Source Separation Tool

CaptainStems is a cross-platform GUI application built in Python that allows users to separate audio tracks into their component stems (vocals, instruments, etc.) using AI-powered source separation.

## Project Overview

This application provides an easy-to-use interface for audio source separation, a task that typically requires technical knowledge or command-line expertise. With CaptainStems, users can:

1. Drag and drop audio files or folders into the application
2. Choose from different AI models for audio separation
3. Process one file or a whole queue with a single click
4. Listen to the separated stems and save them in the format they need

## Technical Details

### Technology Stack

- **UI Framework**: PyQt6 - Provides a modern, cross-platform GUI, including audio playback (Qt Multimedia)
- **Audio Processing** (each in its own environment, see below):
  - Demucs 4.1 (Meta Research) - Hybrid Transformer Demucs (v4) and Hybrid Demucs (v3) models
  - Spleeter 2.4 (Deezer Research) - Fast TensorFlow based separation
  - Band-Split RoFormer via python-audio-separator - Highest quality vocal separation
  - D3Net (Sony AI Research) - Official pretrained networks, run with ONNX Runtime
- **Audio Libraries**:
  - FFmpeg - Decoding of input files and export of stems (system installation or the copy bundled with imageio-ffmpeg)
  - soundfile and NumPy - Reading audio for the waveform display

### Python Version Compatibility

| Python Version | Compatibility      | Notes                                                |
| -------------- | ------------------ | ---------------------------------------------------- |
| 3.10.x         | ✅ **Recommended** | Every model can be installed                         |
| 3.9.x          | ⚠️ Limited         | Spleeter and D3Net only                              |
| 3.11.x         | ⚠️ Limited         | Everything except D3Net                              |
| 3.12.x         | ⚠️ Limited         | Demucs and Band-Split RoFormer only                  |
| 3.13.x         | ⚠️ Limited         | Models need a second Python installation or uv       |

Each model declares the Python versions its packages support. If the interpreter running the application
is not one of them, `core/envs.py` looks for another interpreter (`py -3.10` on Windows, `python3.10` on the
PATH) and finally falls back to `uv venv --python`.

### Architecture

The application follows a Model-View-Controller (MVC) pattern:

- **Models**: Located in the `models/` directory, these wrap the separation backends
- **Views**: Located in the `ui/` directory, these handle the user interface
- **Controller**: `ui/main_window.py` orchestrates the application flow, using the services in `core/`

#### Isolated model environments

The separation libraries pin incompatible dependencies (Spleeter needs NumPy < 1.24 with TensorFlow 2.12,
NNabla needs NumPy 1.26, python-audio-separator needs NumPy 2). They can not be installed side by side, so
every backend gets its own virtual environment below the application data directory, created on demand by
`core/envs.py`. The application environment itself only contains PyQt6, NumPy and soundfile.

Consequences of this design:

- Models are always run as subprocesses with the Python of their environment
- Installing a model can not break the application or another model
- Uninstalling a model is deleting its environment and weights folder
- An environment counts as installed only once a marker file was written at the end of a successful
  installation, so interrupted installations are never used

#### Processing pipeline

`core/pipeline.py` implements the workflow shared by the GUI and the command line:

1. FFmpeg decodes the input into 16-bit 44.1 kHz stereo WAV (`mix.wav`)
2. `BaseModel.process()` runs the backend and collects one `<stem>.wav` per stem
3. The result (`SeparationResult`) is shown in the results window and/or exported with FFmpeg

Backends report progress either through their progress bars (parsed by `core.process.BarProgress`) or,
for the runner scripts in `models/runners/`, through `PROGRESS`/`STATUS` lines on stdout.

### File Structure

```
CaptainStems/
├── main.py                  # Application entry point
├── captain.py               # Unified entrypoint: launch, setup, model installation, command line separation
├── run.py                   # Launcher with dependency checks (same as captain.py without arguments)
├── start.bat                # Windows launcher
├── start.sh                 # macOS/Linux launcher
├── setup_compatible_env.sh  # Creates a Python 3.10 environment (macOS/Linux)
├── start_compatible.sh      # Launches with the Python 3.10 environment
├── install_*.py             # Shortcuts for captain.py --install-model
├── requirements.txt         # Dependencies of the application itself
├── requirements-dev.txt     # Dependencies for running the tests
├── core/                    # Services without user interface
│   ├── paths.py             # Application data and temporary directories
│   ├── process.py           # Subprocesses with live output, cancellation and progress parsing
│   ├── envs.py              # Isolated environments for the model backends
│   ├── ffmpeg.py            # FFmpeg discovery, conversion and export
│   ├── audio.py             # Waveform envelopes
│   ├── pipeline.py          # The separation workflow
│   └── settings.py          # Persistent preferences
├── models/                  # Audio separation models
│   ├── base_model.py        # Common interface and processing workflow
│   ├── registry.py          # Catalog of model families and factory
│   ├── demucs_model.py
│   ├── spleeter_model.py
│   ├── bandsplit_model.py
│   ├── d3net_model.py
│   └── runners/             # Scripts executed inside the model environments
│       ├── spleeter_runner.py
│       └── d3net_runner.py
├── ui/                      # User interface components
│   ├── main_window.py       # Model selection, file queue, processing
│   ├── drop_area.py
│   ├── results_window.py    # Waveforms, playback, saving
│   ├── waveform.py
│   ├── model_selection_dialog.py
│   ├── manage_models_dialog.py
│   ├── install_dialog.py
│   ├── settings_dialog.py
│   ├── workers.py           # Background threads
│   └── styles/dark_mode.py  # Light and dark theme
└── test/                    # Test suite (pytest)
```

## Getting Started

### Running the Application

1. Ensure you have Python installed (3.10 recommended)
2. Clone this repository
3. Start the application:

   - **Windows**: `start.bat`
   - **macOS/Linux**: `./start.sh`, or `./setup_compatible_env.sh` followed by `./start_compatible.sh` to use a dedicated Python 3.10 environment

4. Alternatively, for a manual installation:
   ```
   pip install -r requirements.txt
   python run.py
   ```

### Development Setup

1. Create a Python 3.10 virtual environment (recommended):

   ```
   python3.10 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:

   ```
   pip install -r requirements-dev.txt
   ```

3. Run the application and the tests:

   ```
   python main.py
   python -m pytest
   ```

4. Install the models you want to work with, from the application or with:

   ```
   python captain.py --install-model demucs
   ```

## Using the Application without Models

The application starts without any model installed:

1. Launch the application normally
2. Models that are not installed are marked "(not installed)" in the model list
3. Select one and click "Install Model" to install it from within the application
4. "Manage Models..." shows all model families, their disk usage, and lets you uninstall them

## Adding New Models

To add a new audio separation model:

1. Create a new file in the `models/` directory with a class derived from `BaseModel`
2. Set `BACKEND` (the name of its environment) and `PYTHON_VERSIONS`, and list the variants in `AVAILABLE_MODELS` and `SEPARATION_MODES`
3. Implement `_install()` (pip packages for its environment) and `_separate()` (run the backend on a WAV file and return the stems it wrote)
4. Register it as a `ModelFamily` in `models/registry.py`

If the backend has no usable command line, add a runner script to `models/runners/` that is executed with
the Python of the model's environment and reports `PROGRESS <percent>` and `STATUS <text>` lines.

## License

This project is licensed under the MIT License.
