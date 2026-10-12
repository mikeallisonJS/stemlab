#!/usr/bin/env python3
"""
Band-Split RoFormer Installation Script for CaptainStems

Installs Band-Split RoFormer into its own isolated environment.
Equivalent to: python captain.py --install-model bandsplit
"""

import sys

from captain import main

if __name__ == "__main__":
    sys.exit(main(["--install-model", "bandsplit"]))
