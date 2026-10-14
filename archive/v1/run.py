#!/usr/bin/env python3
"""
Launcher script for CaptainStems.
This script ensures that all dependencies are installed before running the application.
"""

import sys

from captain import main

if __name__ == "__main__":
    # captain.py checks the dependencies, installs missing ones and starts the application
    sys.exit(main())
