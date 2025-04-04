# CaptainStems

A cross-platform Python GUI application for audio source separation using AI models.

## Features

- Drag and drop interface for audio files
- Support for multiple AI models (Demucs v3/v4, Spleeter, Band-Split RNN, and D3Net)
- Interactive results window with waveform display and audio playback
- Save separated audio stems to your local machine
- Support for a wide range of audio formats (MP3, WAV, FLAC, OGG, M4A, AAC, AIFF, WMA, etc.)

## Installation

### Option 1: Recommended - Use Python 3.10 (Most Compatible)

Demucs, Spleeter, and their dependencies work best with Python 3.10. Use our setup script to create a compatible environment:

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

   **Option A: Use the dedicated installer scripts**

   ```
   # For Demucs v4 (default)
   python install_demucs.py

   # For Demucs v3
   python install_demucs.py --version 3

   # For Spleeter
   python install_spleeter.py

   # For Band-Split RNN
   python install_bandsplit.py

   # For D3Net
   python install_d3net.py
   ```

   These scripts provide a guided installation process with platform-specific options.

   **Option B: Manual installation**

   ```
   # First install NumPy 1.x (important for compatibility)
   pip install "numpy>=1.24.0,<2.0.0"

   # For Demucs models:
   # Then install PyTorch and torchaudio
   pip install torch==2.0.1 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cpu
   # Then install Demucs (v4 or v3)
   pip install demucs==4.0.1 ffmpeg-python
   # Or for Demucs v3
   pip install demucs==3.0.6 ffmpeg-python

   # For Spleeter models:
   pip install tensorflow==2.12.0 spleeter==2.4.0 ffmpeg-python

   # For Band-Split RNN models:
   pip install torch==2.0.1 torchaudio==2.0.2 band-split-rnn ffmpeg-python

   # For D3Net models:
   pip install torch==2.0.1 torchaudio==2.0.2 audiofile ffmpeg-python
   # Clone and install D3Net from source:
   git clone https://github.com/sony/ai-research-code.git
   cd ai-research-code/d3net
   pip install -e .
   ```

   **Option C: Install from within the application**

   The application allows you to install models directly from the UI when needed.

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

You can also specify which models to install with flags:

```
# For Demucs v3
./fix_compatibility.sh --demucs-v3

# For Spleeter
./fix_compatibility.sh --spleeter

# For Band-Split RNN
./fix_compatibility.sh --bandsplit-rnn

# For D3Net
./fix_compatibility.sh --d3net

# For multiple models
./fix_compatibility.sh --spleeter --bandsplit-rnn --d3net
```

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

### Visualizing and Playing Stems

After processing an audio file:

1. A results window will automatically open showing the separated stems
2. Each stem displays a waveform visualization
3. Use the play/pause button to listen to individual stems
4. The time slider allows you to navigate through the audio
5. Click the "Save" button on any stem to save it to your preferred location
6. Use the "Save All Files" button to save all stems to a directory of your choice

## Supported Audio Formats

With FFmpeg installed, CaptainStems supports a wide range of audio formats:

- Common formats: MP3, WAV, FLAC, OGG, M4A, AAC
- Additional formats: WMA, AIFF, APE, OPUS, MIDI, and many more

If an audio format is not directly supported by the separation models, it will be automatically converted to WAV format before processing.

## Supported Models

### Demucs v4 Models (Default)

- **htdemucs**: Hybrid Transformer Demucs (default)
- **htdemucs_ft**: Hybrid Transformer Demucs fine-tuned
- **htdemucs_6s**: Hybrid Transformer Demucs for 6 sources separation (drums, bass, other, vocals, piano, guitar)

### Demucs v3 Models (Legacy)

- **demucs**: Original Demucs v3 model
- **demucs_extra**: Demucs v3 with extra training
- **demucs_quantized**: Smaller Demucs v3 model
- **tasnet**: Conv-TasNet model
- **tasnet_extra**: Conv-TasNet with extra training

### Spleeter Models

- **2stems**: Separates audio into vocals and accompaniment
- **4stems**: Separates audio into vocals, drums, bass, and other
- **5stems**: Separates audio into vocals, drums, bass, piano, and other

### Band-Split RNN Models

- **standard**: Standard 4-source separation (vocals, drums, bass, other)
- **light**: Lightweight 4-source separation (smaller model, faster processing)

### D3Net Models

- **standard**: Standard 4-source separation model (vocals, drums, bass, other)
- **optimized**: Optimized version with better performance (same 4 stems)

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

You can also specify which models to install with flags:

```
# For Demucs v3
./fix_compatibility.sh --demucs-v3

# For Spleeter
./fix_compatibility.sh --spleeter

# For Band-Split RNN
./fix_compatibility.sh --bandsplit-rnn

# For D3Net
./fix_compatibility.sh --d3net

# For multiple models
./fix_compatibility.sh --spleeter --bandsplit-rnn --d3net
```

### Installation Issues

If you encounter issues installing dependencies:

1. **Recommended solution**: Use the Python 3.10 compatible environment:

   ```
   ./setup_compatible_env.sh
   ```

2. Check your Python version:

   - Demucs, Spleeter, and their ML dependencies work best with Python 3.10
   - Python 3.11+ may have compatibility issues with some dependencies

3. Platform-specific issues:

   - **Apple Silicon (M1/M2 Macs)**: Use `pip install torch==2.0.1 torchaudio==2.0.2` without extra flags
   - **Windows/Linux**: Use `pip install torch==2.0.1 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cpu`

4. For more help, check the detailed installation guide in [PROJECT.md](PROJECT.md)

## License

MIT
