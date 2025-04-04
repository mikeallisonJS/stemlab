#!/bin/bash

# CaptainStems Compatibility Fix Script
# This script fixes NumPy and PyTorch compatibility issues

set -e  # Exit on error

# Colorful output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== CaptainStems Compatibility Fix Script ===${NC}"
echo "This script will fix NumPy and PyTorch compatibility issues."

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
        ./setup_compatible_env.sh
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

echo "NumPy version: $NUMPY_VERSION"
echo "PyTorch version: $TORCH_VERSION"

if [[ $NUMPY_VERSION == 2* ]]; then
    echo -e "${YELLOW}NumPy 2.x detected. This is incompatible with PyTorch.${NC}"
    echo "Fixing compatibility issues..."
    
    # Uninstall potentially problematic packages
    echo "Uninstalling PyTorch, torchaudio, and Demucs..."
    pip uninstall -y torch torchaudio demucs
    
    # Uninstall numpy and reinstall numpy 1.x
    echo "Uninstalling NumPy 2.x and installing NumPy 1.x..."
    pip uninstall -y numpy
    pip install "numpy>=1.24.0,<2.0.0"
    
    # Install compatible PyTorch version
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
    
    # Install Demucs
    echo "Installing Demucs..."
    pip install demucs==4.0.1
    
    echo -e "${GREEN}Compatibility issues fixed!${NC}"
else
    echo -e "${GREEN}NumPy version is compatible with PyTorch.${NC}"
    
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
    
    # Check if Demucs is installed
    if ! pip show demucs &>/dev/null; then
        echo "Demucs not installed. Installing..."
        pip install demucs==4.0.1
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

# Deactivate virtual environment
deactivate 