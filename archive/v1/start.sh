#!/bin/bash

# CaptainStems startup script
# This script launches the CaptainStems application

# Determine script location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Prefer Python 3.10: it is the version every model supports
if command -v python3.10 &> /dev/null; then
    PYTHON=python3.10
elif command -v python3 &> /dev/null; then
    PYTHON=python3
else
    echo "Python 3 is not installed. Please install Python 3.10 to use CaptainStems."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment with $PYTHON..."
    "$PYTHON" -m venv venv || exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Run the application (installs missing dependencies first)
echo "Starting CaptainStems..."
python captain.py "$@"
STATUS=$?

# Deactivate virtual environment on exit
deactivate
exit $STATUS
