#!/usr/bin/env python3
"""
D3Net Installation Script for CaptainStems

Installs D3Net into its own isolated environment.
Equivalent to: python captain.py --install-model d3net
"""

import sys

from captain import main

if __name__ == "__main__":
    sys.exit(main(["--install-model", "d3net"]))
