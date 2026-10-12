#!/usr/bin/env python3
"""
Demucs Installation Script for CaptainStems

Installs Demucs into its own isolated environment.
Equivalent to: python captain.py --install-model demucs
"""

import argparse
import sys

from captain import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Install Demucs for CaptainStems")
    # Kept for compatibility: one Demucs package provides both the v3 and v4 models
    parser.add_argument("--version", type=int, choices=[3, 4], default=4,
                        help="Demucs model generation (both are installed together)")
    parser.parse_args()
    sys.exit(main(["--install-model", "demucs"]))
