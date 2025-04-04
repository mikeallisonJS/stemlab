#!/bin/bash
# Startup script for CaptainStems with Python 3.10 environment

# Activate virtual environment
source venv_py310/bin/activate

# Run the application
python run.py

# Deactivate virtual environment on exit
deactivate
