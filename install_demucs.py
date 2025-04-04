#!/usr/bin/env python3
"""
Demucs Installation Script for CaptainStems

This script provides a guided installation process for Demucs and its dependencies.
It offers platform-specific installation options and troubleshooting guidance.
"""

import os
import sys
import platform
import subprocess
import argparse

def print_section(title):
    """Print a section header."""
    print("\n" + "="*60)
    print(title)
    print("="*60)

def check_python_version():
    """Check Python version and print warning if needed."""
    major, minor, _ = platform.python_version_tuple()
    if int(major) == 3 and int(minor) >= 11:
        print_section("Python Version Warning")
        print(f"Detected Python {major}.{minor}")
        print("Demucs may have compatibility issues with Python 3.11+")
        print("If installation fails, consider using Python 3.10")
        return False
    return True

def check_installed_packages():
    """Check if required packages are already installed."""
    try:
        import pkg_resources
        
        installed = {}
        for package in ['torch', 'torchaudio', 'demucs', 'numpy']:
            try:
                dist = pkg_resources.get_distribution(package)
                installed[package] = dist.version
            except pkg_resources.DistributionNotFound:
                installed[package] = None
        
        return installed
    except ImportError:
        print("Installing setuptools...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "setuptools"])
        import pkg_resources
        return check_installed_packages()

def install_numpy():
    """Install NumPy 1.x explicitly (required for PyTorch compatibility)."""
    print("Installing NumPy 1.x (required for PyTorch compatibility)...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "numpy>=1.24.0,<2.0.0"],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        print(f"Error installing NumPy: {result.stderr}")
        return False
    
    print("NumPy installation completed.")
    return True

def install_pytorch(cpu_only=True, platform_specific=True):
    """Install PyTorch and torchaudio with specific versions."""
    print("Installing PyTorch and torchaudio...")
    
    # Determine platform-specific installation
    is_mac_arm = platform.system() == "Darwin" and platform.machine() == "arm64"
    
    # First install with --no-deps to prevent numpy upgrade
    if is_mac_arm and platform_specific:
        # M1/M2 Mac - use default PyTorch
        cmd_no_deps = [
            sys.executable, "-m", "pip", "install", 
            "torch==2.0.1", "torchaudio==2.0.2", "--no-deps"
        ]
        cmd_full = [
            sys.executable, "-m", "pip", "install", 
            "torch==2.0.1", "torchaudio==2.0.2"
        ]
        print("Using Apple Silicon (M1/M2) specific installation...")
    elif cpu_only:
        # CPU only
        cmd_no_deps = [
            sys.executable, "-m", "pip", "install",
            "torch==2.0.1", "torchaudio==2.0.2", "--no-deps",
            "--index-url", "https://download.pytorch.org/whl/cpu"
        ]
        cmd_full = [
            sys.executable, "-m", "pip", "install",
            "torch==2.0.1", "torchaudio==2.0.2",
            "--index-url", "https://download.pytorch.org/whl/cpu"
        ]
        print("Using CPU-only PyTorch installation...")
    else:
        # Default installation (may include CUDA)
        cmd_no_deps = [
            sys.executable, "-m", "pip", "install", 
            "torch==2.0.1", "torchaudio==2.0.2", "--no-deps"
        ]
        cmd_full = [
            sys.executable, "-m", "pip", "install", 
            "torch==2.0.1", "torchaudio==2.0.2"
        ]
        print("Using default PyTorch installation...")
    
    # First install with no deps
    result = subprocess.run(cmd_no_deps, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error during first PyTorch installation step: {result.stderr}")
    
    # Then install with deps
    result = subprocess.run(cmd_full, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error installing PyTorch: {result.stderr}")
        return False
    
    print("PyTorch installation completed.")
    return True

def install_demucs(version=4):
    """Install Demucs."""
    print(f"Installing Demucs v{version}...")
    
    # Determine the version to install
    if version == 3:
        demucs_version = "demucs==3.0.6"
        # Demucs v3 requires torch 1.8.1 and torchaudio 0.8.1, but we'll use 2.0.1 for compatibility
        # It should still work with the newer torch
    else:
        demucs_version = "demucs==4.0.1"
    
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", demucs_version],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        print(f"Error installing Demucs: {result.stderr}")
        return False
    
    print(f"Demucs v{version} installation completed.")
    return True

def verify_installation():
    """Verify that packages are installed correctly."""
    installed = check_installed_packages()
    
    if all(installed.values()):
        print_section("Installation Successful")
        print("All packages are installed:")
        for package, version in installed.items():
            print(f"  - {package}: {version}")
        return True
    else:
        print_section("Installation Incomplete")
        print("The following packages were not installed:")
        for package, version in installed.items():
            if not version:
                print(f"  - {package}")
        return False

def print_troubleshooting():
    """Print troubleshooting information."""
    print_section("Troubleshooting Guide")
    print("If you encountered errors during installation:")
    
    print("\n1. Try installing with conda instead:")
    print("   conda install -c pytorch pytorch=2.0.1 torchaudio=2.0.2 numpy=1.24.4")
    print("   conda install -c conda-forge demucs=4.0.1")
    
    print("\n2. For Python 3.11+ compatibility issues:")
    print("   Consider creating a Python 3.10 virtual environment:")
    print("   python3.10 -m venv venv_py310")
    print("   source venv_py310/bin/activate  # On Windows: venv_py310\\Scripts\\activate")
    print("   pip install -r requirements.txt")
    
    print("\n3. NumPy/PyTorch compatibility issues:")
    print("   Make sure to install NumPy 1.x BEFORE installing PyTorch:")
    print("   pip install \"numpy>=1.24.0,<2.0.0\"")
    print("   pip install torch==2.0.1 torchaudio==2.0.2")
    
    print("\n4. For Demucs v3 specific support:")
    print("   You can install v3 with: pip install demucs==3.0.6")
    
    print("\n5. Visit the official documentation:")
    print("   PyTorch: https://pytorch.org/get-started/locally/")
    print("   Demucs: https://github.com/facebookresearch/demucs")

def main():
    """Main function to run the installation."""
    parser = argparse.ArgumentParser(description="Install Demucs and its dependencies")
    parser.add_argument("--cpu-only", action="store_true", help="Install CPU-only version of PyTorch")
    parser.add_argument("--skip-platform-specific", action="store_true", 
                        help="Skip platform-specific installations (e.g., for M1/M2 Macs)")
    parser.add_argument("--version", type=int, choices=[3, 4], default=4,
                        help="Demucs version to install (3 or 4, default: 4)")
    args = parser.parse_args()
    
    print_section(f"Demucs v{args.version} Installer for CaptainStems")
    
    # Check Python version
    check_python_version()
    
    # Check what's already installed
    installed = check_installed_packages()
    print("Current package status:")
    for package, version in installed.items():
        status = f"v{version}" if version else "not installed"
        print(f"  - {package}: {status}")
    
    # Ask user to proceed
    if all(installed.values()):
        print("\nAll required packages are already installed.")
        choice = input("Would you like to reinstall them? (y/n): ")
        if choice.lower() != 'y':
            print("Installation skipped.")
            return
    else:
        choice = input("\nProceed with installation? (y/n): ")
        if choice.lower() != 'y':
            print("Installation cancelled.")
            return
    
    # First install NumPy 1.x to prevent compatibility issues
    if not installed['numpy'] or installed['numpy'].startswith('2.'):
        if not install_numpy():
            print("NumPy installation failed. This will likely cause issues with PyTorch.")
            print_troubleshooting()
            return
    
    # Install PyTorch if needed
    if not installed['torch'] or not installed['torchaudio']:
        if not install_pytorch(
            cpu_only=args.cpu_only, 
            platform_specific=not args.skip_platform_specific
        ):
            print("PyTorch installation failed.")
            print_troubleshooting()
            return
    
    # Install Demucs if needed
    if not installed['demucs']:
        if not install_demucs(version=args.version):
            print("Demucs installation failed.")
            print_troubleshooting()
            return
    
    # Verify installation
    if verify_installation():
        print("\nYou can now run CaptainStems with full functionality!")
        if args.version == 3:
            print("\nDemucs v3 models available: demucs, demucs_extra, demucs_quantized, tasnet, tasnet_extra")
        else:
            print("\nDemucs v4 models available: htdemucs, htdemucs_ft, htdemucs_6s")
    else:
        print_troubleshooting()

if __name__ == "__main__":
    main() 