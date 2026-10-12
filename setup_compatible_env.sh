#!/bin/bash

# CaptainStems Environment Setup Script
# This script creates a virtual environment with Python 3.10, the version
# every model supports, and installs the application's dependencies into it.
#
# The AI models themselves are installed later, each into its own isolated
# environment: from the application, or with the flags below.

set -e  # Exit on error

# Colorful output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Parse command line arguments
MODELS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --demucs|--demucs-v3)
            MODELS+=("demucs")
            shift
            ;;
        --spleeter)
            MODELS+=("spleeter")
            shift
            ;;
        --bandsplit|--bandsplit-rnn)
            MODELS+=("bandsplit")
            shift
            ;;
        --d3net)
            MODELS+=("d3net")
            shift
            ;;
        --all)
            MODELS=("all")
            shift
            ;;
        -h|--help)
            echo "Usage: ./setup_compatible_env.sh [--demucs] [--spleeter] [--bandsplit] [--d3net] [--all]"
            echo "Creates the Python 3.10 environment and optionally installs models."
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}Setting up CaptainStems with Python 3.10${NC}"

# Check if Python 3.10 is installed
if ! command -v python3.10 &> /dev/null; then
    echo -e "${RED}Python 3.10 was not found.${NC}"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "Install it with Homebrew:  brew install python@3.10"
    else
        echo "Install it with your package manager, for example:"
        echo "  sudo apt install python3.10 python3.10-venv"
    fi
    echo "Or download it from https://www.python.org/downloads/"
    exit 1
fi

# FFmpeg is optional: the application bundles a copy
if command -v ffmpeg &> /dev/null; then
    echo -e "${GREEN}FFmpeg is installed${NC}"
else
    echo -e "${YELLOW}FFmpeg is not installed system-wide. The bundled copy will be used.${NC}"
fi

# Create virtual environment
if [ ! -d "venv_py310" ]; then
    echo "Creating virtual environment in venv_py310..."
    python3.10 -m venv venv_py310
fi

source venv_py310/bin/activate
python -m pip install --upgrade pip
python captain.py --setup

for MODEL in "${MODELS[@]}"; do
    python captain.py --install-model "$MODEL"
done

deactivate

echo
echo -e "${GREEN}Setup complete.${NC} Start the application with:"
echo "  ./start_compatible.sh"
