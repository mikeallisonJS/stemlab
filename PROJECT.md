# CaptainStems - Audio Source Separation Tool

CaptainStems is a cross-platform GUI application built in Python that allows users to separate audio tracks into their component stems (vocals, instruments, etc.) using AI-powered source separation.

## Project Overview

This application provides an easy-to-use interface for audio source separation, a task that typically requires technical knowledge or command-line expertise. With CaptainStems, users can:

1. Drag and drop audio files into the application
2. Choose from different AI models for audio separation
3. Process the audio with a single click
4. Save the separated stems to their computer

## Technical Details

### Technology Stack

- **UI Framework**: PyQt6 - Provides a modern, cross-platform GUI
- **Audio Processing**:
  - Demucs v4 (Facebook Research) - State-of-the-art audio source separation
  - More models can be added in the future
- **Audio Libraries**:
  - librosa - For audio analysis
  - soundfile - For audio I/O

### Python Version Compatibility

CaptainStems can run on different Python versions, but there are important compatibility considerations:

| Python Version | Compatibility      | Notes                                          |
| -------------- | ------------------ | ---------------------------------------------- |
| 3.10.x         | ✅ **Recommended** | Best compatibility with Demucs and PyTorch     |
| 3.9.x          | ✅ Good            | Works with most versions of PyTorch and Demucs |
| 3.11.x         | ⚠️ Limited         | Some versions of PyTorch may not support 3.11  |
| 3.12.x, 3.13.x | ⚠️ Problematic     | PyTorch and Demucs likely won't work properly  |

**For best results:**

- Use Python 3.10 with our `setup_compatible_env.sh` script
- For newer Python versions, you may still use the application's UI features, but AI model functionality might be limited

### Architecture

The application follows a Model-View-Controller (MVC) pattern:

- **Models**: Located in the `models/` directory, these handle the audio processing logic
- **Views**: Located in the `ui/` directory, these handle the user interface
- **Controller**: The main application code acts as the controller

### File Structure

```
CaptainStems/
├── main.py                # Main application entry point
├── run.py                 # Launcher with dependency checks
├── start.sh               # Shell script launcher
├── setup_compatible_env.sh # Sets up Python 3.10 environment
├── install_demucs.py      # Dedicated Demucs installer
├── requirements.txt       # Python dependencies
├── models/                # Audio processing models
│   ├── __init__.py
│   └── demucs_model.py
└── ui/                    # User interface components
    ├── __init__.py
    ├── main_window.py
    └── drop_area.py
```

## Getting Started

### Running the Application

1. Ensure you have Python installed (3.10 recommended)
2. Clone this repository
3. For best compatibility, use:

   ```
   ./setup_compatible_env.sh
   ```

   Then run:

   ```
   ./start_compatible.sh
   ```

4. Alternatively, for standard installation:
   ```
   pip install -r requirements.txt
   python run.py
   ```

### Development Setup

1. Create a Python 3.10 virtual environment (recommended):

   ```
   python3.10 -m venv venv_py310
   source venv_py310/bin/activate  # On Windows: venv_py310\Scripts\activate
   ```

2. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Install optional dependencies (for audio processing):

   **Standard Install**:

   ```bash
   pip install torch torchaudio demucs
   ```

   **Platform-Specific Installation**:

   - **For CPU-only (recommended for most users)**:

     ```bash
     pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
     pip install demucs
     ```

   - **For Apple Silicon (M1/M2 Macs)**:

     ```bash
     pip install torch torchaudio
     pip install demucs
     ```

   - **Using Conda**:

     ```bash
     conda install -c pytorch pytorch torchaudio
     conda install -c conda-forge demucs
     ```

   - **For GPU support**:
     Visit https://pytorch.org/get-started/locally/ for specific installation instructions.

### Troubleshooting Installation

If you encounter errors installing Demucs or PyTorch:

1. Try installing PyTorch and torchaudio first, then install Demucs separately
2. Use a conda environment instead of venv if you have Conda installed
3. For Python 3.11+, use our `setup_compatible_env.sh` script to create a Python 3.10 environment
4. Visit the [Demucs GitHub repository](https://github.com/facebookresearch/demucs) for the latest installation instructions

## Using the Application without Optional Dependencies

The application can be used without installing Demucs:

1. Launch the application normally
2. You will see an "Install Model" button next to uninstalled models
3. Click this button to install the model from within the application
4. Alternatively, you can install the dependencies manually and restart the application

## Adding New Models

To add a new audio separation model:

1. Create a new file in the `models/` directory
2. Implement a class with the same interface as `DemucsModel`
3. Add the model to the `models` dictionary in `main_window.py`

## License

This project is licensed under the MIT License - see the LICENSE file for details.
