#!/usr/bin/env python3
"""
Spleeter Installation Script for CaptainStems

Installs Spleeter into its own isolated environment.
Equivalent to: python captain.py --install-model spleeter
"""

import sys

from captain import main

if __name__ == "__main__":
    sys.exit(main(["--install-model", "spleeter"]))
