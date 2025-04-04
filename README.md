# CaptainStems

A cross-platform Python GUI application for audio source separation using AI models.

## Features

- Drag and drop interface for audio files
- Support for multiple AI models (currently Demucs v4)
- Save separated audio stems to your local machine
- Support for a wide range of audio formats (MP3, WAV, FLAC, OGG, M4A, AAC, AIFF, WMA, etc.)

## Installation

### Option 1: Recommended - Use Python 3.10 (Most Compatible)

Demucs and PyTorch work best with Python 3.10. Use our setup script to create a compatible environment:

```bash
./setup_compatible_env.sh
```

This script will:

1. Check if Python 3.10 is installed (or help you install it)
2. Check for FFmpeg and offer to install it (required for audio format conversion)
3. Create a new virtual environment with Python 3.10
4. Install all dependencies including PyTorch and Demucs
5. Create a startup script for the compatible environment

### Option 2: Standard Installation

1. Clone this repository
2. Install the dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Install optional AI model dependencies:

   **Option A: Use the dedicated installer script**

   ```
   python install_demucs.py
   ```

   This script provides a guided installation process with platform-specific options.

   **Option B: Manual installation**

   ```
   pip install "numpy>=1.24.0,<2.0.0"  # Important: Install NumPy 1.x first
   pip install torch==2.0.1 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cpu
   pip install demucs==4.0.1 ffmpeg-python
   ```

   **Option C: Install from within the application**

   The application allows you to install Demucs directly from the UI when needed.

## NumPy/PyTorch Compatibility Fix

If you get errors related to NumPy 2.x and PyTorch compatibility, run the fix script:

```bash
./fix_compatibility.sh
```

This script will:

1. Check your current virtual environment
2. Detect NumPy 2.x if installed
3. Uninstall incompatible packages
4. Install the correct versions of NumPy, PyTorch, and Demucs

## External Dependencies

For full audio format support, you need FFmpeg installed on your system:

- **macOS**: `brew install ffmpeg`
- **Ubuntu/Debian**: `sudo apt install ffmpeg`
- **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH

## Usage

If you used the compatible environment setup:

```
./start_compatible.sh
```

Otherwise, run the application with:

```
python run.py
```

Or use the provided shell script:

```
./start.sh
```

## Supported Audio Formats

With FFmpeg installed, CaptainStems supports a wide range of audio formats:

- Common formats: MP3, WAV, FLAC, OGG, M4A, AAC
- Additional formats: WMA, AIFF, APE, OPUS, MIDI, and many more

If an audio format is not directly supported by Demucs, it will be automatically converted to WAV format before processing.

## Troubleshooting

### NumPy & PyTorch Compatibility

PyTorch requires NumPy 1.x. If you see error messages about NumPy 2.x compatibility:

```
A module that was compiled using NumPy 1.x cannot be run in NumPy 2.1.3 as it may crash
```

Run the compatibility fix script:

```
./fix_compatibility.sh
```

### Installation Issues

If you encounter other issues installing Demucs or PyTorch:

1. **Recommended solution**: Use the Python 3.10 compatible environment:

   ```
   ./setup_compatible_env.sh
   ```

2. Check your Python version:

   - Demucs and PyTorch work best with Python 3.10
   - Python 3.11+ may have compatibility issues with some dependencies

3. Platform-specific issues:

   - **Apple Silicon (M1/M2 Macs)**: Use `pip install torch==2.0.1 torchaudio==2.0.2` without extra flags
   - **Windows/Linux**: Use `pip install torch==2.0.1 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cpu`

4. For more help, check the detailed installation guide in [PROJECT.md](PROJECT.md)

## Supported Models

- [Demucs v4](https://github.com/facebookresearch/demucs) - Facebook Research's music source separation model

## License

MIT
