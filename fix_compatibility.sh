#!/bin/bash

# CaptainStems Compatibility Fix Script
# This script fixes NumPy and PyTorch compatibility issues

set -e  # Exit on error

# Colorful output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Define variables
INSTALL_DEMUCS=true
INSTALL_DEMUCS_V3=false
INSTALL_SPLEETER=false
INSTALL_BANDSPLIT_RNN=false
INSTALL_D3NET=false
INSTALL_TENSORFLOW_METAL=false

# Parse command line arguments
for arg in "$@"
do
    case "$arg" in
        --demucs-v3)
            INSTALL_DEMUCS_V3=true
            ;;
        --spleeter)
            INSTALL_SPLEETER=true
            ;;
        --bandsplit-rnn)
            INSTALL_BANDSPLIT_RNN=true
            ;;
        --d3net)
            INSTALL_D3NET=true
            ;;
        --tensorflow-metal)
            INSTALL_TENSORFLOW_METAL=true
            ;;
        --help)
            echo "Usage: ./fix_compatibility.sh [options]"
            echo "Options:"
            echo "  --demucs-v3       Install Demucs v3 models"
            echo "  --spleeter        Install Spleeter models"
            echo "  --bandsplit-rnn   Install Band-Split RNN models"
            echo "  --d3net           Install D3Net models"
            echo "  --tensorflow-metal Install tensorflow-metal for Apple Silicon Macs"
            echo "  --help            Show this help message"
            exit 0
            ;;
    esac
done

# Check if we're on Apple Silicon Mac
IS_APPLE_SILICON=false
if [[ "$(uname)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
    IS_APPLE_SILICON=true
    echo "Detected Apple Silicon Mac"
    
    # Automatically enable tensorflow-metal if we're on Apple Silicon
    if [[ "$INSTALL_SPLEETER" == "true" && "$INSTALL_TENSORFLOW_METAL" != "true" ]]; then
        INSTALL_TENSORFLOW_METAL=true
        echo "Enabling tensorflow-metal support for Spleeter on Apple Silicon"
    fi
fi

echo -e "${GREEN}=== CaptainStems Compatibility Fix Script ===${NC}"
echo "This script will fix NumPy and PyTorch compatibility issues."
echo "It will remove incompatible versions and install the correct ones."
echo ""
echo "Models to install:"
echo "- Demucs v4: $INSTALL_DEMUCS"
if [[ "$INSTALL_DEMUCS_V3" == "true" ]]; then
    echo "- Demucs v3: $INSTALL_DEMUCS_V3"
fi
if [[ "$INSTALL_SPLEETER" == "true" ]]; then
    echo "- Spleeter: $INSTALL_SPLEETER"
fi
if [[ "$INSTALL_BANDSPLIT_RNN" == "true" ]]; then
    echo "- Band-Split RNN: $INSTALL_BANDSPLIT_RNN"
fi
if [[ "$INSTALL_D3NET" == "true" ]]; then
    echo "- D3Net: $INSTALL_D3NET"
fi
if [[ "$INSTALL_TENSORFLOW_METAL" == "true" ]]; then
    echo "- tensorflow-metal: $INSTALL_TENSORFLOW_METAL"
fi
echo ""

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
        if [ "$INSTALL_DEMUCS_V3" = true ]; then
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

# Check if we're in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "WARNING: You are not in a virtual environment."
    echo "It's recommended to create and activate a virtual environment before running this script."
    echo "Continue anyway? (y/n)"
    read -r response
    if [[ "$response" != "y" ]]; then
        echo "Exiting..."
        exit 1
    fi
else
    echo "Using virtual environment: $VIRTUAL_ENV"
fi

# Check for NumPy 2.x
echo -n "Checking for NumPy 2.x... "
NUMPY_MAJOR_VERSION=$(echo "$NUMPY_VERSION" | cut -d. -f1)
if [[ "$NUMPY_MAJOR_VERSION" == "2" ]]; then
    echo "Found NumPy $NUMPY_VERSION"
    echo "NumPy 2.x is not compatible with PyTorch. Will downgrade to NumPy 1.x."
    HAS_NUMPY_2=true
else
    echo "NumPy 2.x not found"
    HAS_NUMPY_2=false
fi

# If NumPy 2.x is installed or force reinstall, clean up packages
if [[ "$HAS_NUMPY_2" == "true" ]]; then
    echo ""
    echo "Removing incompatible packages..."
    
    # Uninstall in reverse dependency order
    if [[ -n "$DEMUCS_VERSION_INSTALLED" ]]; then
        echo "Removing demucs..."
        pip uninstall -y demucs
    fi
    
    if [[ -n "$SPLEETER_VERSION" ]]; then
        echo "Removing spleeter..."
        pip uninstall -y spleeter
    fi
    
    if [[ -n "$TENSORFLOW_METAL" ]]; then
        echo "Removing tensorflow-metal..."
        pip uninstall -y tensorflow-metal
    fi
    
    if [[ -n "$TENSORFLOW_VERSION" ]]; then
        echo "Removing tensorflow..."
        pip uninstall -y tensorflow
    fi
    
    if [[ -n "$TORCH_VERSION" ]]; then
        echo "Removing torch..."
        pip uninstall -y torch
    fi
    
    # Install NumPy 1.x
    echo ""
    echo "Installing NumPy 1.x..."
    pip install "numpy>=1.24.0,<2.0.0"
else
    # Ensure NumPy 1.x is installed
    if [[ -z "$NUMPY_VERSION" ]]; then
        echo "Installing NumPy 1.x..."
        pip install "numpy>=1.24.0,<2.0.0"
    fi
fi

# Install PyTorch and torchaudio
if [[ "$INSTALL_DEMUCS" == "true" || "$INSTALL_DEMUCS_V3" == "true" || "$INSTALL_BANDSPLIT_RNN" == "true" || "$INSTALL_D3NET" == "true" || -z "$TORCH_VERSION" ]]; then
    echo ""
    echo "Installing PyTorch and torchaudio..."
    
    # Use platform-specific commands for installation
    if [[ "$IS_APPLE_SILICON" == "true" ]]; then
        # Apple Silicon (M1/M2) Mac
        pip install torch==2.0.1 torchaudio==2.0.2
    else
        # Other platforms (Intel Mac, Windows, Linux)
        pip install torch==2.0.1 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cpu
    fi
fi

# Install TensorFlow and tensorflow-metal if needed
if [[ "$INSTALL_SPLEETER" == "true" || -z "$TENSORFLOW_VERSION" ]]; then
    echo ""
    echo "Installing TensorFlow..."
    
    if [[ "$IS_APPLE_SILICON" == "true" && "$INSTALL_TENSORFLOW_METAL" == "true" ]]; then
        # Install TensorFlow with Metal support for Apple Silicon
        echo "Installing TensorFlow with Metal GPU support for Apple Silicon..."
        pip install tensorflow-macos==2.12.0 tensorflow-metal>=0.7.0
    else
        # Standard TensorFlow for other platforms
        pip install tensorflow==2.12.0
    fi
fi

# Install Demucs (v4 by default, or v3 if specified)
if [[ "$INSTALL_DEMUCS" == "true" ]]; then
    echo ""
    if [[ "$INSTALL_DEMUCS_V3" == "true" ]]; then
        echo "Installing Demucs v3..."
        pip install demucs==3.0.6
    else
        echo "Installing Demucs v4..."
        pip install demucs==4.0.1
    fi
fi

# Install Spleeter if specified
if [[ "$INSTALL_SPLEETER" == "true" ]]; then
    echo ""
    echo "Installing Spleeter..."
    pip install spleeter==2.4.0
fi

# Install Band-Split RNN if specified
if [[ "$INSTALL_BANDSPLIT_RNN" == "true" ]]; then
    echo ""
    echo "Installing Band-Split RNN..."
    pip install band-split-rnn
fi

# Install D3Net if specified
if [[ "$INSTALL_D3NET" == "true" ]]; then
    echo ""
    echo "Installing D3Net..."
    pip install git+https://github.com/sony/ai-research-code.git#subdirectory=d3net
fi

# Verify installation success
echo ""
echo "Checking final package versions..."

# Check NumPy
NUMPY_VERSION=$(python -c "import numpy; print(numpy.__version__)" 2>/dev/null)
if [[ -n "$NUMPY_VERSION" ]]; then
    echo "NumPy: $NUMPY_VERSION"
else
    echo "NumPy: Not installed"
fi

# Check PyTorch
TORCH_VERSION=$(python -c "import torch; print(torch.__version__)" 2>/dev/null)
if [[ -n "$TORCH_VERSION" ]]; then
    echo "PyTorch: $TORCH_VERSION"
else
    echo "PyTorch: Not installed"
fi

# Check TensorFlow and tensorflow-metal
TF_VERSION=$(python -c "import tensorflow; print(tensorflow.__version__)" 2>/dev/null)
if [[ -n "$TF_VERSION" ]]; then
    echo "TensorFlow: $TF_VERSION"
    
    # Check for Metal support on Apple Silicon
    if [[ "$IS_APPLE_SILICON" == "true" && "$INSTALL_TENSORFLOW_METAL" == "true" ]]; then
        TF_METAL_VERSION=$(python -c "import tensorflow_metal; print('Installed')" 2>/dev/null)
        if [[ -n "$TF_METAL_VERSION" ]]; then
            echo "tensorflow-metal: Installed"
            # Check if Metal devices are available
            METAL_DEVICES=$(python -c "import tensorflow as tf; devices = tf.config.list_physical_devices(); print('Metal GPU: ' + str(any('METAL' in str(d).upper() for d in devices)))" 2>/dev/null)
            echo "$METAL_DEVICES"
        else
            echo "tensorflow-metal: Not installed"
        fi
    fi
else
    echo "TensorFlow: Not installed"
fi

# Check Demucs
DEMUCS_VERSION=$(python -c "import demucs; print('Installed')" 2>/dev/null)
if [[ -n "$DEMUCS_VERSION" ]]; then
    echo "Demucs: Installed"
else
    echo "Demucs: Not installed"
fi

# Check Spleeter
SPLEETER_VERSION=$(python -c "import spleeter; print('Installed')" 2>/dev/null)
if [[ -n "$SPLEETER_VERSION" ]]; then
    echo "Spleeter: Installed"
else
    echo "Spleeter: Not installed"
fi

# Check Band-Split RNN
BANDSPLIT_VERSION=$(python -c "import band_split_rnn; print('Installed')" 2>/dev/null)
if [[ -n "$BANDSPLIT_VERSION" ]]; then
    echo "Band-Split RNN: Installed"
else
    echo "Band-Split RNN: Not installed"
fi

# Check D3Net (less reliable since it might not have a Python module)
D3NET_VERSION=$(python -c "import d3net; print('Installed')" 2>/dev/null)
if [[ -n "$D3NET_VERSION" ]]; then
    echo "D3Net: Installed"
else
    echo "D3Net: Installation status unknown (may be installed but not as a Python module)"
fi

echo ""
echo "Compatibility fix complete!"
echo "If you encounter any issues, please try creating a new virtual environment."

# Deactivate virtual environment
deactivate 