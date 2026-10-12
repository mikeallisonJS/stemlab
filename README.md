# CaptainStems

A cross-platform Python GUI application for audio source separation using AI models.

## Features

- Drag and drop interface for audio files and folders, with a queue for batch processing
- Support for multiple AI models (Demucs v3/v4, Spleeter, Band-Split RoFormer, and D3Net)
- Each model family installs into its own isolated environment, straight from the application
- Interactive results window with waveform display and audio playback, including the original mix for comparison
- Save separated audio stems as WAV, FLAC, AIFF, MP3, M4A or OGG, optionally automatically after processing
- Support for a wide range of audio formats (MP3, WAV, FLAC, OGG, M4A, AAC, AIFF, WMA, etc.) and the audio track of video files
- GPU acceleration: NVIDIA (CUDA), any DirectX 12 GPU for D3Net on Windows, and Metal on Apple Silicon
- Light and dark theme, and settings that are remembered between sessions
- Command line mode for separating files without the user interface

## Installation

CaptainStems needs **Python 3.10** for full model support (see [Python versions](#python-versions)).

### Windows

Double-click `start.bat`, or run it from a terminal:

```
start.bat
```

It creates a virtual environment on first use, installs the dependencies and starts the application.

### macOS and Linux

```bash
./start.sh
```

This does the same using `python3.10` if available, otherwise `python3`. If your default Python is newer
than 3.10, create a dedicated Python 3.10 environment instead:

```bash
./setup_compatible_env.sh
./start_compatible.sh
```

### Manual installation

```
pip install -r requirements.txt
python run.py
```

`requirements.txt` only contains the application itself (PyQt6, NumPy, soundfile and a bundled FFmpeg).
The AI models are installed separately, as described next.

## Installing models

Nothing needs to be installed up front. Select a model in the application and click **Install Model**,
or open **Manage Models...** to install and uninstall model families and see how much disk space they use.

Models can also be installed from the command line:

```
python captain.py --install-model demucs      # Demucs v3 and v4
python captain.py --install-model spleeter
python captain.py --install-model bandsplit   # Band-Split RoFormer
python captain.py --install-model d3net
python captain.py --install-model all

python captain.py --uninstall-model spleeter  # remove one again
python captain.py --check                     # show what is installed
```

The scripts `install_demucs.py`, `install_spleeter.py`, `install_bandsplit.py` and `install_d3net.py` do the same.

### How models are installed

The separation libraries require mutually incompatible versions of NumPy, PyTorch and TensorFlow, so they
cannot share one Python environment. CaptainStems therefore gives every model family its own virtual
environment and runs the models as separate processes:

| Platform | Location of environments and model weights            |
| -------- | ----------------------------------------------------- |
| Windows  | `%LOCALAPPDATA%\CaptainStems`                         |
| macOS    | `~/Library/Application Support/CaptainStems`          |
| Linux    | `~/.local/share/CaptainStems`                         |

Set the `CAPTAINSTEMS_HOME` environment variable to use a different location.

Installing or removing a model never changes the environment the application runs in, and uninstalling a
model simply deletes its folder. If a model stops working, uninstall and reinstall it.

| Model family        | Download size                    | Runs on                                    |
| ------------------- | -------------------------------- | ------------------------------------------ |
| Demucs (v3 and v4)  | ~5 GB with NVIDIA GPU, ~1.5 GB without | NVIDIA GPU (CUDA), Apple GPU, or CPU |
| Spleeter            | ~1.5 GB                          | CPU (fast)                                 |
| Band-Split RoFormer | ~6 GB with NVIDIA GPU, ~2 GB without, plus ~650 MB per model | NVIDIA GPU (CUDA), Apple GPU, or CPU (slow) |
| D3Net               | ~700 MB                          | Any DirectX 12 GPU on Windows, otherwise CPU (slow) |

## Usage

1. Drag audio files or folders into the window (or click the drop area to browse)
2. Select a model. **Advanced Models...** offers every variant with a description
3. Click **Process Audio**. Progress is shown per file, and processing can be cancelled
4. When a single file is done its results window opens. In a batch, double-click a finished file to open its results

### Visualizing and Playing Stems

After processing an audio file:

1. A results window shows the original mix and the separated stems
2. Each track displays a waveform visualization
3. Use the play/pause buttons to listen to a track
4. Click a waveform to jump to that position. Switching to another track continues from the same position,
   which makes it easy to compare stems with each other and with the original
5. Choose a format and click "Save..." on any stem to save it to your preferred location
6. Use the "Save All Files..." button to save all stems into a folder named after the track and model

### Settings

**Settings...** lets you change:

- the theme (follow the system, dark or light)
- the default format and bitrate for saving stems
- automatic saving of all stems after processing, next to the source file or into an output folder
- the device to process on (automatic, CPU only, NVIDIA GPU, Apple GPU)
- Demucs quality options (number of shifts, overlap) and Wiener filtering for Spleeter

### Command line

Files can be separated without the user interface:

```
python captain.py --separate song.mp3
python captain.py --separate *.flac --model htdemucs_ft --format mp3 --bitrate 320k --output stems/
python captain.py --separate song.wav --model bandsplit:vocals
python captain.py --separate song.wav --two-stems
python captain.py --list-models
```

## GPU Acceleration

#### NVIDIA GPUs

When an NVIDIA GPU is detected, Demucs and Band-Split RoFormer are installed with the CUDA build of PyTorch.
Only a current NVIDIA driver is required; the CUDA libraries are part of the installation.

#### Windows (any GPU)

D3Net runs through DirectML and uses any DirectX 12 capable GPU, including AMD and Intel ones.

#### Apple Silicon Macs (M1/M2/M3)

CaptainStems detects Apple Silicon Macs and installs `tensorflow-macos` and `tensorflow-metal` for Spleeter,
which avoids the AVX instruction errors of the standard TensorFlow package. PyTorch based models can use the
Apple GPU: select "Apple GPU (MPS)" as the device in the settings.

#### CPU

Everything also runs without a GPU. Spleeter is fast on a CPU, Demucs takes a few minutes per song, and
Band-Split RoFormer and D3Net are slow.

## External Dependencies

FFmpeg is used to read and write audio files. A copy is installed with the application, so nothing needs
to be set up. If FFmpeg is installed system-wide it is preferred:

- **macOS**: `brew install ffmpeg`
- **Ubuntu/Debian**: `sudo apt install ffmpeg`
- **Windows**: `winget install Gyan.FFmpeg`

## Supported Audio Formats

CaptainStems reads every audio format FFmpeg supports:

- Common formats: MP3, WAV, FLAC, OGG, M4A, AAC
- Additional formats: WMA, AIFF, APE, OPUS, AC3, and many more
- Video files (MP4, MOV, MKV, WEBM, AVI): the audio track is used

Every file is converted to 44.1 kHz stereo before processing. Stems can be saved as WAV, FLAC, AIFF, MP3,
M4A (AAC) or OGG (Vorbis).

## Supported Models

### Demucs v4 Models (Default)

- **htdemucs**: Hybrid Transformer Demucs (default)
- **htdemucs_ft**: Hybrid Transformer Demucs fine-tuned (best quality, takes four times as long)
- **htdemucs_6s**: Hybrid Transformer Demucs for 6 sources separation (drums, bass, other, vocals, piano, guitar)

### Demucs v3 Models (Legacy)

- **hdemucs_mmi**: Hybrid Demucs trained on MusDB plus 800 additional songs
- **mdx**: Hybrid Demucs trained on MusDB only, winner of track A of the MDX challenge
- **mdx_extra**: Hybrid Demucs trained with extra data, the best v3 model

All Demucs models offer the "vocals/instrumental only" option.

### Spleeter Models

- **2stems**: Separates audio into vocals and accompaniment
- **4stems**: Separates audio into vocals, drums, bass, and other
- **5stems**: Separates audio into vocals, drums, bass, piano, and other

### Band-Split RoFormer Models

- **vocals**: Vocals and instrumental, the highest quality vocal separation offered here
- **6stems**: Vocals, drums, bass, guitar, piano, and other

Band-Split RoFormer is the successor of Band-Split RNN. It is used here because, unlike Band-Split RNN,
pretrained models for it are publicly available (through
[python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator)).

### D3Net Models

- **standard**: 4-source separation model (vocals, drums, bass, other)
- **fast**: The same model without channel-swap averaging: half the processing time, slightly lower quality

D3Net uses [Sony's official implementation](https://github.com/sony/ai-research-code/tree/master/d3net) and
pretrained networks, converted to ONNX during installation.

## Python versions

| Python version | Compatibility      | Notes                                                        |
| -------------- | ------------------ | ------------------------------------------------------------ |
| 3.10.x         | ✅ **Recommended** | Every model can be installed                                 |
| 3.9.x          | ⚠️ Limited         | Spleeter and D3Net only                                      |
| 3.11.x         | ⚠️ Limited         | Everything except D3Net                                      |
| 3.12.x         | ⚠️ Limited         | Demucs and Band-Split RoFormer only                          |
| 3.13.x         | ⚠️ Limited         | The application runs; models need a second Python (see below) |

When the application runs on a Python version a model does not support, it looks for a suitable Python
installation (the `py` launcher on Windows, `python3.10` on the PATH) or uses [uv](https://docs.astral.sh/uv/)
to create the model's environment. If none is found, the installation explains what is missing.

## Troubleshooting

### A model fails to install

The installation window shows the complete installer output. Common causes:

- No internet connection, or not enough disk space (see the download sizes above)
- A Python version the model does not support: install Python 3.10
- On Windows, very long installation paths: set `CAPTAINSTEMS_HOME` to a short path such as `C:\CaptainStems`

### A model fails during processing

Open **Manage Models...**, uninstall the model family and install it again. This recreates its environment
from scratch without affecting anything else.

### Out of memory on the GPU

Select "CPU only" as the device in the settings, or use a smaller model (for example `htdemucs` instead of
`htdemucs_ft`).

### TensorFlow AVX Instruction Errors

On Apple Silicon Macs the standard TensorFlow package fails with:

```
The TensorFlow library was compiled to use AVX instructions, but these aren't available on your machine.
```

CaptainStems installs `tensorflow-macos` for Spleeter on these machines. If you see this error, make sure
the application runs on a Python built for ARM64 (not under Rosetta), then reinstall Spleeter.

## Development

Run the tests with:

```
pip install -r requirements-dev.txt
python -m pytest
```

The tests that run the real models are skipped by default, see [test/README.md](test/README.md).
More about the architecture is in [PROJECT.md](PROJECT.md).

## License

MIT
