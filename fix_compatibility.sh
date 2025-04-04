#!/bin/bash

# CaptainStems Compatibility Fix Script
# This script fixes NumPy and PyTorch compatibility issues

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

echo -e "${GREEN}=== CaptainStems Compatibility Fix Script ===${NC}"
echo "This script will fix NumPy and PyTorch compatibility issues."
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

# Check for virtual environment
if [ -d "venv_py310" ]; then
    VENV_DIR="venv_py310"
    echo -e "${GREEN}Found Python 3.10 virtual environment.${NC}"
elif [ -d "venv" ]; then
    VENV_DIR="venv"
    echo -e "${GREEN}Found standard virtual environment.${NC}"
else
    echo -e "${YELLOW}No virtual environment found.${NC}"
    echo "Would you like to create a new one with setup_compatible_env.sh? (y/n)"
    read -r create_venv
    if [[ $create_venv == "y" ]]; then
        cmd="./setup_compatible_env.sh"
        if [ "$DEMUCS_VERSION" -eq 3 ]; then
            cmd="$cmd --demucs-v3"
        fi
        if [ "$INSTALL_SPLEETER" = true ]; then
            cmd="$cmd --spleeter"
        fi
        if [ "$INSTALL_BANDSPLIT_RNN" = true ]; then
            cmd="$cmd --bandsplit-rnn"
        fi
        if [ "$INSTALL_D3NET" = true ]; then
            cmd="$cmd --d3net"
        fi
        $cmd
        exit 0
    else
        echo -e "${RED}No virtual environment found. Please create one first.${NC}"
        exit 1
    fi
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

# Check current versions
echo "Checking current versions..."
NUMPY_VERSION=$(pip show numpy 2>/dev/null | grep Version | awk '{print $2}' || echo "not installed")
TORCH_VERSION=$(pip show torch 2>/dev/null | grep Version | awk '{print $2}' || echo "not installed")
DEMUCS_VERSION_INSTALLED=$(pip show demucs 2>/dev/null | grep Version | awk '{print $2}' || echo "not installed")
SPLEETER_VERSION=$(pip show spleeter 2>/dev/null | grep Version | awk '{print $2}' || echo "not installed")
TENSORFLOW_VERSION=$(pip show tensorflow 2>/dev/null | grep Version | awk '{print $2}' || echo "not installed")
BANDSPLIT_VERSION=$(pip show band-split-rnn 2>/dev/null | grep Version | awk '{print $2}' || echo "not installed")
D3NET_VERSION="not installed"
if pip show d3net &>/dev/null; then
    D3NET_VERSION="installed"
fi

echo "NumPy version: $NUMPY_VERSION"
echo "PyTorch version: $TORCH_VERSION"
echo "TensorFlow version: $TENSORFLOW_VERSION"
echo "Demucs version: $DEMUCS_VERSION_INSTALLED"
echo "Spleeter version: $SPLEETER_VERSION"
echo "Band-Split RNN version: $BANDSPLIT_VERSION"
echo "D3Net version: $D3NET_VERSION"

if [[ $NUMPY_VERSION == 2* ]]; then
    echo -e "${YELLOW}NumPy 2.x detected. This is incompatible with PyTorch and TensorFlow.${NC}"
    echo "Fixing compatibility issues..."
    
    # Uninstall potentially problematic packages
    echo "Uninstalling ML packages that require NumPy 1.x..."
    pip uninstall -y torch torchaudio demucs tensorflow spleeter band-split-rnn d3net
    
    # Uninstall numpy and reinstall numpy 1.x
    echo "Uninstalling NumPy 2.x and installing NumPy 1.x..."
    pip uninstall -y numpy
    pip install "numpy>=1.24.0,<2.0.0"
    
    # Install compatible PyTorch version for Demucs
    echo "Installing compatible PyTorch version..."
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
    
    # Install Demucs with the specified version
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
    
    echo -e "${GREEN}Compatibility issues fixed!${NC}"
else
    echo -e "${GREEN}NumPy version is compatible with PyTorch and TensorFlow.${NC}"
    
    # Still check if PyTorch and Demucs are installed
    if [[ $TORCH_VERSION == "not installed" ]]; then
        echo "PyTorch not installed. Installing compatible version..."
        if [[ $(uname -m) == "arm64" && $(uname -s) == "Darwin" ]]; then
            # M1/M2 Mac
            echo "Detected Apple Silicon (M1/M2 Mac). Using native PyTorch..."
            pip install torch==2.0.1 torchaudio==2.0.2
        else
            # Non-M1 Mac or other systems
            echo "Using CPU-only PyTorch..."
            pip install torch==2.0.1 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cpu
        fi
    fi
    
    # Check if Demucs is installed or if we need to change version
    if [[ $DEMUCS_VERSION_INSTALLED == "not installed" ]]; then
        if [ "$DEMUCS_VERSION" -eq 3 ]; then
            echo "Demucs not installed. Installing Demucs v3..."
            pip install demucs==3.0.6
        else
            echo "Demucs not installed. Installing Demucs v4..."
            pip install demucs==4.0.1
        fi
    elif [[ $DEMUCS_VERSION_INSTALLED == 3* && "$DEMUCS_VERSION" -eq 4 ]]; then
        echo "Updating from Demucs v3 to v4..."
        pip uninstall -y demucs
        pip install demucs==4.0.1
    elif [[ $DEMUCS_VERSION_INSTALLED == 4* && "$DEMUCS_VERSION" -eq 3 ]]; then
        echo "Downgrading from Demucs v4 to v3..."
        pip uninstall -y demucs
        pip install demucs==3.0.6
    fi
    
    # Check if Spleeter is installed and install if requested
    if [ "$INSTALL_SPLEETER" = true ] && [[ $SPLEETER_VERSION == "not installed" ]]; then
        echo "Installing TensorFlow and Spleeter..."
        
        # First check if TensorFlow is installed
        if [[ $TENSORFLOW_VERSION == "not installed" ]]; then
            pip install tensorflow==2.12.0
        fi
        
        # Install Spleeter
        pip install spleeter==2.4.0
    fi
    
    # Check if Band-Split RNN is installed and install if requested
    if [ "$INSTALL_BANDSPLIT_RNN" = true ] && [[ $BANDSPLIT_VERSION == "not installed" ]]; then
        echo "Installing Band-Split RNN..."
        
        # Install ffmpeg-python if not installed
        if ! pip show ffmpeg-python &>/dev/null; then
            pip install ffmpeg-python
        fi
        
        # Install Band-Split RNN
        pip install band-split-rnn
    fi
    
    # Check if D3Net is installed and install if requested
    if [ "$INSTALL_D3NET" = true ] && [[ $D3NET_VERSION == "not installed" ]]; then
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
fi

# Check other required packages
if ! pip show ffmpeg-python &>/dev/null; then
    echo "Installing ffmpeg-python..."
    pip install ffmpeg-python
fi

echo -e "${GREEN}CaptainStems dependencies are now properly configured.${NC}"
echo "You can now run the application with:"
echo "  source $VENV_DIR/bin/activate"
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