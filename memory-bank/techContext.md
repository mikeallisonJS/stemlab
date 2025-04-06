# CaptainStems - Technical Context

## Technology Stack

### Core Technologies

- **Python**: Primary programming language (3.10.x recommended)
- **PyQt6**: Cross-platform GUI framework
- **FFmpeg**: Audio processing and format conversion

### AI Models

- **Demucs v4** (Facebook Research): State-of-the-art audio source separation
- **Demucs v3** (Legacy): Older version with different separation characteristics
- **Spleeter** (Deezer Research): Alternative separation model
- **Band-Split RNN**: Specialized audio separation model
- **D3Net** (Sony AI Research): High-quality separation model

### Audio Libraries

- **librosa**: Audio analysis and waveform processing
- **soundfile/audiofile**: Audio I/O operations
- **PyTorch/torchaudio**: Deep learning framework for audio processing
- **TensorFlow**: Required for Spleeter model

### Development Tools

- **pip**: Python package manager
- **venv**: Virtual environment management
- **setuptools**: Package building utilities

## Development Setup

### Recommended Environment

- Python 3.10.x virtual environment
- FFmpeg installed at system level
- IDE with Python support (VS Code, PyCharm, etc.)

### Environment Setup Scripts

- `setup_compatible_env.sh`: Creates Python 3.10 environment with all dependencies
- `fix_compatibility.sh`: Resolves NumPy/PyTorch compatibility issues
- `start_compatible.sh`: Launches application with compatible environment

### Installation Process

The application has a multi-layered installation approach:

1. Core dependencies via requirements.txt
2. Optional AI model dependencies via dedicated scripts
3. In-application installation of missing dependencies

## Technical Constraints

### Python Version Compatibility

| Python Version | Compatibility  | Notes                                 |
| -------------- | -------------- | ------------------------------------- |
| 3.10.x         | ✅ Recommended | Best compatibility with all AI models |
| 3.9.x          | ✅ Good        | Compatible with most AI models        |
| 3.11.x         | ⚠️ Limited     | Some AI models may not work properly  |
| 3.12.x, 3.13.x | ⚠️ Problematic | Most AI models likely won't work      |

### Platform-Specific Considerations

- **macOS**:

  - Special handling for Apple Silicon (M1/M2/M3)
  - Metal GPU acceleration for TensorFlow (Spleeter)
  - Different PyTorch installation approach

- **Windows**:
  - Path handling differences
  - FFmpeg installation challenges
  - Different PyTorch installation requirements

### Dependencies Challenges

- **NumPy 2.x Compatibility**: PyTorch requires NumPy 1.x
- **GPU Acceleration**: Different approaches needed per platform
- **C Extensions**: Some dependencies require compiler toolchain

## External Dependencies

### FFmpeg

- Required for handling various audio formats
- Used by multiple AI models for audio processing
- Installation methods vary by platform

### AI Model Weights

- Downloaded automatically during first use
- Can be substantial in size (multiple GB total)
- Cached for future use

## Technical Roadmap Considerations

- Support for newer Python versions as AI models evolve
- Additional AI model integration as they become available
- Performance optimizations for large audio files
- Enhanced GPU acceleration support
