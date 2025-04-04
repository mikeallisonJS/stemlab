#!/usr/bin/env python3
"""
Spleeter Installation Script for CaptainStems

This script provides a guided installation process for Spleeter and its dependencies.
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
        print("Spleeter may have compatibility issues with Python 3.11+")
        print("If installation fails, consider using Python 3.10")
        return False
    return True

def check_installed_packages():
    """Check if required packages are already installed."""
    try:
        import pkg_resources
        
        installed = {}
        for package in ['tensorflow', 'spleeter', 'numpy']:
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
    """Install NumPy 1.x explicitly (required for TensorFlow compatibility)."""
    print("Installing NumPy 1.x (required for TensorFlow compatibility)...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "numpy>=1.24.0,<2.0.0"],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        print(f"Error installing NumPy: {result.stderr}")
        return False
    
    print("NumPy installation completed.")
    return True

def install_tensorflow(cpu_only=True):
    """Install TensorFlow and related dependencies."""
    print("Installing TensorFlow...")
    
    # Install TensorFlow CPU version by default
    tensorflow_package = "tensorflow==2.12.0"
    
    # First install with --no-deps to prevent numpy upgrade
    cmd_no_deps = [
        sys.executable, "-m", "pip", "install",
        tensorflow_package, "--no-deps"
    ]
    
    cmd_full = [
        sys.executable, "-m", "pip", "install",
        tensorflow_package
    ]
    
    # First install with no deps
    result = subprocess.run(cmd_no_deps, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error during first TensorFlow installation step: {result.stderr}")
    
    # Then install with deps
    result = subprocess.run(cmd_full, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error installing TensorFlow: {result.stderr}")
        return False
    
    print("TensorFlow installation completed.")
    return True

def install_spleeter():
    """Install Spleeter."""
    print("Installing Spleeter...")
    
    # Specify Spleeter version for compatibility
    spleeter_version = "spleeter==2.4.0"
    
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", spleeter_version],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        print(f"Error installing Spleeter: {result.stderr}")
        return False
    
    print("Spleeter installation completed.")
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

def install_ffmpeg_python():
    """Install the ffmpeg-python package for audio handling."""
    print("Installing ffmpeg-python...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "ffmpeg-python"],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        print(f"Warning: Error installing ffmpeg-python: {result.stderr}")
        print("Audio conversion features may be limited.")
        return False
    
    return True

def print_troubleshooting():
    """Print troubleshooting information."""
    print_section("Troubleshooting Guide")
    print("If you encountered errors during installation:")
    
    print("\n1. Try installing with conda instead:")
    print("   conda install -c conda-forge numpy=1.24.4 tensorflow=2.12.0")
    print("   conda install -c conda-forge spleeter ffmpeg-python")
    
    print("\n2. For Python 3.11+ compatibility issues:")
    print("   Consider creating a Python 3.10 virtual environment:")
    print("   python3.10 -m venv venv_py310")
    print("   source venv_py310/bin/activate  # On Windows: venv_py310\\Scripts\\activate")
    print("   pip install -r requirements.txt")
    
    print("\n3. NumPy/TensorFlow compatibility issues:")
    print("   Make sure to install NumPy 1.x BEFORE installing TensorFlow:")
    print("   pip install \"numpy>=1.24.0,<2.0.0\"")
    print("   pip install tensorflow==2.12.0")
    
    print("\n4. Check if FFmpeg is installed on your system:")
    print("   - macOS: brew install ffmpeg")
    print("   - Ubuntu/Debian: sudo apt install ffmpeg")
    print("   - Windows: Download from https://ffmpeg.org/download.html")
    
    print("\n5. Visit the official documentation:")
    print("   Spleeter: https://github.com/deezer/spleeter")
    print("   TensorFlow: https://www.tensorflow.org/install")

def main():
    """Main function to run the installation."""
    parser = argparse.ArgumentParser(description="Install Spleeter and its dependencies")
    args = parser.parse_args()
    
    print_section("Spleeter Installer for CaptainStems")
    
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
            print("NumPy installation failed. This will likely cause issues with TensorFlow.")
            print_troubleshooting()
            return
    
    # Install TensorFlow if needed
    if not installed['tensorflow']:
        if not install_tensorflow():
            print("TensorFlow installation failed.")
            print_troubleshooting()
            return
    
    # Install Spleeter if needed
    if not installed['spleeter']:
        if not install_spleeter():
            print("Spleeter installation failed.")
            print_troubleshooting()
            return
    
    # Install ffmpeg-python
    install_ffmpeg_python()
    
    # Verify installation
    if verify_installation():
        print("\nYou can now run CaptainStems with Spleeter functionality!")
        print("\nAvailable Spleeter models:")
        print("  - 2stems: Vocals and accompaniment separation")
        print("  - 4stems: Vocals, drums, bass, and other separation")
        print("  - 5stems: Vocals, drums, bass, piano, and other separation")
    else:
        print_troubleshooting()

if __name__ == "__main__":
    main() 