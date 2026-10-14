#!/bin/bash
# Startup script for CaptainStems with Python 3.10 environment

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

if [ ! -d "venv_py310" ]; then
    echo "The Python 3.10 environment does not exist yet. Run ./setup_compatible_env.sh first."
    exit 1
fi

# Activate virtual environment
source venv_py310/bin/activate

# Run the application
python captain.py "$@"
STATUS=$?

# Deactivate virtual environment on exit
deactivate
exit $STATUS
