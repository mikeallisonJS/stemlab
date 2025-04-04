#!/bin/bash

# CaptainStems Environment Setup Script
# This script creates a compatible virtual environment with Python 3.10
# for use with Demucs and PyTorch

set -e  # Exit on error

# Colorful output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Parse command line arguments
DEMUCS_VERSION=4
INSTALL_SPLEETER=false
INSTALL_BANDSPLIT_RNN=false
INSTALL_D3NET=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --demucs-v3)
            DEMUCS_VERSION=3
            shift
            ;;
        --spleeter)
            INSTALL_SPLEETER=true
            shift
            ;;
        --bandsplit-rnn)
            INSTALL_BANDSPLIT_RNN=true
            shift
            ;;
        --d3net)
            INSTALL_D3NET=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Valid options:"
            echo "  --demucs-v3      Install Demucs v3 instead of v4"
            echo "  --spleeter       Install Spleeter models"
            echo "  --bandsplit-rnn  Install Band-Split RNN models"
            echo "  --d3net          Install D3Net models"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}=== CaptainStems Compatible Environment Setup ===${NC}"
echo "This script will create a Python 3.10 virtual environment for CaptainStems."
if [ "$DEMUCS_VERSION" -eq 3 ]; then
    echo "Demucs v3 will be installed."
else
    echo "Demucs v4 will be installed (default)."
fi

if [ "$INSTALL_SPLEETER" = true ]; then
    echo "Spleeter will also be installed."
fi

if [ "$INSTALL_BANDSPLIT_RNN" = true ]; then
    echo "Band-Split RNN will also be installed."
fi

if [ "$INSTALL_D3NET" = true ]; then
    echo "D3Net will also be installed."
fi

# Check for ffmpeg
check_ffmpeg() {
    if command -v ffmpeg &> /dev/null; then
        echo -e "${GREEN}FFmpeg found.${NC}"
        return 0
    else
        echo -e "${YELLOW}FFmpeg not found. FFmpeg is required for audio format conversion.${NC}"
        return 1
    fi
}

install_ffmpeg() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            echo "Installing FFmpeg using Homebrew..."
            brew install ffmpeg
        else
            echo -e "${YELLOW}Homebrew not found. Please install FFmpeg manually:${NC}"
            echo "  - Visit: https://ffmpeg.org/download.html"
            echo "  - Or install Homebrew (https://brew.sh) and run: brew install ffmpeg"
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v apt-get &> /dev/null; then
            echo "Installing FFmpeg using apt..."
            sudo apt-get update
            sudo apt-get install -y ffmpeg
        elif command -v dnf &> /dev/null; then
            echo "Installing FFmpeg using dnf..."
            sudo dnf install -y ffmpeg
        else
            echo -e "${YELLOW}Package manager not found. Please install FFmpeg manually:${NC}"
            echo "  - For Ubuntu/Debian: sudo apt-get install ffmpeg"
            echo "  - For Fedora: sudo dnf install ffmpeg"
            echo "  - For other distributions: https://ffmpeg.org/download.html"
        fi
    elif [[ "$OSTYPE" == "msys"* ]] || [[ "$OSTYPE" == "cygwin"* ]]; then
        # Windows
        echo -e "${YELLOW}Please install FFmpeg manually on Windows:${NC}"
        echo "  1. Download from: https://ffmpeg.org/download.html"
        echo "  2. Add FFmpeg to your system PATH"
    else
        echo -e "${YELLOW}Unknown operating system. Please install FFmpeg manually:${NC}"
        echo "  - Visit: https://ffmpeg.org/download.html"
    fi
}

# Check for FFmpeg
if ! check_ffmpeg; then
    echo -e "${YELLOW}Would you like to install FFmpeg now? (y/n)${NC}"
    read -r install_ffmpeg_choice
    if [[ $install_ffmpeg_choice == "y" ]]; then
        install_ffmpeg
        # Verify installation
        if ! check_ffmpeg; then
            echo -e "${YELLOW}FFmpeg installation might not have succeeded. The script will continue, but audio conversion features may be limited.${NC}"
        fi
    else
        echo -e "${YELLOW}FFmpeg installation skipped. Audio conversion features will be limited.${NC}"
    fi
fi

# Check if Python 3.10 is installed
if command -v python3.10 &> /dev/null; then
    echo -e "${GREEN}Python 3.10 found.${NC}"
    PYTHON_CMD="python3.10"
else
    echo -e "${YELLOW}Python 3.10 not found. Checking for alternatives...${NC}"
    
    # Try to find Python 3.10.x
    for ver in {0..9}; do
        if command -v python3.10.${ver} &> /dev/null; then
            echo -e "${GREEN}Found Python 3.10.${ver}${NC}"
            PYTHON_CMD="python3.10.${ver}"
            break
        fi
    done
    
    # If still not found, check if brew is installed (macOS)
    if [ -z "$PYTHON_CMD" ] && command -v brew &> /dev/null; then
        echo -e "${YELLOW}Python 3.10 not found. Would you like to install it using Homebrew? (y/n)${NC}"
        read -r install_python
        if [[ $install_python == "y" ]]; then
            echo "Installing Python 3.10 using Homebrew..."
            brew install python@3.10
            PYTHON_CMD="python3.10"
        else
            echo -e "${RED}Python 3.10 is required for this setup. Please install it and try again.${NC}"
            exit 1
        fi
    elif [ -z "$PYTHON_CMD" ]; then
        echo -e "${RED}Python 3.10 is required but not found.${NC}"
        echo "Please install Python 3.10 and try again."
        echo "  - For macOS: brew install python@3.10"
        echo "  - For Ubuntu/Debian: sudo apt install python3.10 python3.10-venv python3.10-dev"
        echo "  - For Windows: download from https://www.python.org/downloads/release/python-3100/"
        exit 1
    fi
fi

# Create venv directory if it doesn't exist
if [ -d "venv_py310" ]; then
    echo -e "${YELLOW}Virtual environment 'venv_py310' already exists.${NC}"
    echo "Would you like to remove it and create a new one? (y/n)"
    read -r recreate_venv
    if [[ $recreate_venv == "y" ]]; then
        echo "Removing existing virtual environment..."
        rm -rf venv_py310
    else
        echo -e "${YELLOW}Using existing virtual environment.${NC}"
    fi
fi

# Create new venv if needed
if [ ! -d "venv_py310" ]; then
    echo "Creating Python 3.10 virtual environment..."
    $PYTHON_CMD -m venv venv_py310
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source venv_py310/bin/activate

# Update pip
echo "Updating pip..."
pip install --upgrade pip setuptools wheel

# First install numpy 1.x specifically to prevent version conflicts
echo "Installing NumPy 1.x (required for PyTorch/TensorFlow compatibility)..."
pip install "numpy>=1.24.0,<2.0.0"

# Install basic requirements
echo "Installing basic requirements..."
pip install -r requirements.txt

# Install PyTorch and Demucs
echo "Installing PyTorch and Demucs..."
if [[ $(uname -m) == "arm64" && $(uname -s) == "Darwin" ]]; then
    # M1/M2 Mac
    echo "Detected Apple Silicon (M1/M2 Mac). Using native PyTorch..."
    pip install torch==2.0.1 torchaudio==2.0.2 --no-deps
    pip install torch==2.0.1 torchaudio==2.0.2
else
    # Non-M1 Mac or other systems
    echo "Using CPU-only PyTorch..."
    pip install torch==2.0.1 torchaudio==2.0.2 --no-deps --index-url https://download.pytorch.org/whl/cpu
    pip install torch==2.0.1 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cpu
fi

# Install Demucs with explicit version
if [ "$DEMUCS_VERSION" -eq 3 ]; then
    echo "Installing Demucs v3..."
    pip install demucs==3.0.6
else
    echo "Installing Demucs v4..."
    pip install demucs==4.0.1
fi

# Install Spleeter if requested
if [ "$INSTALL_SPLEETER" = true ]; then
    echo "Installing TensorFlow and Spleeter..."
    pip install tensorflow==2.12.0 --no-deps
    pip install tensorflow==2.12.0
    pip install spleeter==2.4.0
fi

# Install Band-Split RNN if requested
if [ "$INSTALL_BANDSPLIT_RNN" = true ]; then
    echo "Installing Band-Split RNN..."
    pip install ffmpeg-python
    pip install band-split-rnn
fi

# Install D3Net if requested
if [ "$INSTALL_D3NET" = true ]; then
    echo "Installing D3Net dependencies..."
    pip install audiofile ffmpeg-python
    
    echo "Installing D3Net from source..."
    # Create temporary directory for cloning
    TMP_DIR=$(mktemp -d)
    git clone https://github.com/sony/ai-research-code.git "$TMP_DIR"
    D3NET_DIR="$TMP_DIR/d3net"
    if [ -d "$D3NET_DIR" ]; then
        pip install -e "$D3NET_DIR"
        echo "D3Net installed successfully."
    else
        echo "D3Net installation failed: directory not found."
    fi
fi

# Create start script
echo "Creating startup script..."
cat > start_compatible.sh << 'EOF'
#!/bin/bash
# Startup script for CaptainStems with Python 3.10 environment

# Activate virtual environment
source venv_py310/bin/activate

# Run the application
python run.py

# Deactivate virtual environment on exit
deactivate
EOF

chmod +x start_compatible.sh

echo -e "${GREEN}=== Setup Complete ===${NC}"
echo "A Python 3.10 virtual environment has been created in 'venv_py310'."
echo ""
echo "To use CaptainStems with this environment:"
echo "  ./start_compatible.sh"
echo ""
echo "Or manually:"
echo "  source venv_py310/bin/activate"
echo "  python run.py"

# Show information about installed models
echo ""

if [ "$DEMUCS_VERSION" -eq 3 ]; then
    echo "Demucs v3 was installed with these available models:"
    echo "  - demucs: Original Demucs v3 model"
    echo "  - demucs_extra: Demucs v3 with extra training"
    echo "  - demucs_quantized: Smaller Demucs v3 model"
    echo "  - tasnet: Conv-TasNet model"
    echo "  - tasnet_extra: Conv-TasNet with extra training"
else
    echo "Demucs v4 was installed with these available models:"
    echo "  - htdemucs: Hybrid Transformer Demucs (default)"
    echo "  - htdemucs_ft: Hybrid Transformer Demucs fine-tuned"
    echo "  - htdemucs_6s: Hybrid Transformer Demucs for 6 sources separation"
fi

if [ "$INSTALL_SPLEETER" = true ]; then
    echo ""
    echo "Spleeter was installed with these available models:"
    echo "  - 2stems: Vocals and accompaniment separation"
    echo "  - 4stems: Vocals, drums, bass, and other separation"
    echo "  - 5stems: Vocals, drums, bass, piano, and other separation"
fi

if [ "$INSTALL_BANDSPLIT_RNN" = true ]; then
    echo ""
    echo "Band-Split RNN was installed with these available models:"
    echo "  - standard: Standard 4-source separation (vocals, drums, bass, other)"
    echo "  - light: Lightweight 4-source separation (smaller model)"
fi

if [ "$INSTALL_D3NET" = true ]; then
    echo ""
    echo "D3Net was installed with these available models:"
    echo "  - standard: Standard D3Net model (vocals, drums, bass, other)"
    echo "  - optimized: Optimized version with better performance"
fi

# Deactivate virtual environment
deactivate 