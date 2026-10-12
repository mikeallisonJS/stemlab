# CaptainStems - System Patterns

## Architecture Overview

CaptainStems follows a **Model-View-Controller (MVC)** architecture:

- **Models** (`models/` directory): Wrap the AI separation backends
- **Views** (`ui/` directory): Implement the user interface components
- **Controller** (`ui/main_window.py`): Orchestrates the application flow
- **Services** (`core/` directory): Environments, subprocesses, FFmpeg, pipeline, settings

## Design Patterns

### 1. Factory Pattern

- `models/registry.py` creates model instances from identifiers such as `demucs4:htdemucs`
- Allows for a unified interface across different AI models

### 2. Observer Pattern

- Worker threads (`ui/workers.py`) emit Qt signals for progress, status and results
- Enables progress tracking during lengthy operations without blocking the interface

### 3. Adapter Pattern

- Every model turns its backend's output into the same shape: one `<stem>.wav` per stem
- Runner scripts in `models/runners/` adapt backends without a suitable command line

### 4. Strategy Pattern

- All models implement `BaseModel._separate()`; the surrounding workflow is shared
- Enables easy addition of new separation strategies

### 5. Template Method

- `BaseModel.process()` and `BaseModel.install_dependencies()` define the steps (convert, run,
  collect, clean up / create environment, install, verify, mark) and subclasses fill in the
  backend specific parts

## Key Technical Decisions

### PyQt6 as UI Framework

- Modern cross-platform GUI capabilities
- Native look and feel on both macOS and Windows
- Qt Multimedia for playback, custom painted waveforms instead of a plotting library

### Process isolation for models

- Each backend has its own virtual environment; models run as subprocesses
- Dependency conflicts between backends are impossible, and so is breaking the application
- Cancelling is killing the process tree; a crashing backend can not take the application down
- The price is disk space (each PyTorch based backend carries its own copy)

### Python 3.10 Compatibility

- Primary target for optimal AI model compatibility
- Models declare supported versions; `core/envs.py` finds a matching interpreter

### Installation state

- An environment is "installed" only if its marker file (`captainstems.json`) exists and its
  recipe number matches the code. The marker is written last, so an interrupted installation is
  simply installed again
- Bump a model's `RECIPE` when its packages change to force a reinstall for existing users

## Component Relationships

```
+----------------------+        +--------------------+
| MainWindow           |<------>| DropArea           |
| (Controller)         |        | (View Component)   |
+----------------------+        +--------------------+
     |            |
     |            v
     |    +--------------------+     +--------------------+
     |    | BatchWorker        |---->| core.pipeline      |
     |    | (QThread)          |     | separate / export  |
     |    +--------------------+     +--------------------+
     v                                         |
+----------------------+                       v
| models.registry      |        +--------------------+      +------------------+
| (Factory)            |------->| DemucsModel        |      | BackendEnv       |
+----------------------+------->| SpleeterModel      |----->| (isolated venv,  |
     |                  \------>| BandSplitModel     |      |  subprocess)     |
     |                   \----->| D3NetModel         |      +------------------+
     v                          +--------------------+
+----------------------+        +--------------------+
| ResultsWindow        |<------>| WaveformView       |
| (View)               |<------>| QMediaPlayer       |
+----------------------+        +--------------------+
```

## Error Handling Strategy

- Backends fail in their own process; the end of their output becomes the error message
- Installation failures are shown with the complete installer log
- Working directories are removed after failures and cancellation
- A failed automatic save keeps the separation result, so it can be saved manually
- Invalid files are detected when they are added to the queue, not when processing starts

## Performance Considerations

- Heavy processing runs in subprocesses, driven from background threads
- Real progress from the backends' own progress output
- GPU acceleration where available (CUDA, DirectML, MPS)
- Audio is streamed in blocks when computing waveforms; D3Net's Wiener filter runs in windows to
  bound memory use on long tracks
