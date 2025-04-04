#!/usr/bin/env python3
"""
Launcher script for CaptainStems.
This script ensures that all dependencies are installed before running the application.
"""

import os
import sys
import subprocess
import platform

# First, try to ensure setuptools is installed
try:
    import pkg_resources
except ImportError:
    print("Installing setuptools...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "setuptools"])
    try:
        import pkg_resources
    except ImportError:
        print("Failed to import pkg_resources. Please install setuptools manually.")
        sys.exit(1)

def check_dependencies():
    """Check if all required packages are installed."""
    with open('requirements.txt') as f:
        requirements = [line.strip() for line in f if line.strip()]
    
    missing = []
    for requirement in requirements:
        # Strip version numbers
        package = requirement.split('>=')[0]
        try:
            pkg_resources.get_distribution(package)
        except pkg_resources.DistributionNotFound:
            missing.append(requirement)
    
    return missing

def check_optional_dependencies():
    """Check for optional dependencies like torch and demucs."""
    optional_packages = {
        'torch': 'PyTorch - Deep learning framework needed for audio processing',
        'torchaudio': 'Audio processing library for PyTorch',
        'demucs': 'Facebook Research audio source separation model'
    }
    
    missing = {}
    installed = {}
    
    for package, description in optional_packages.items():
        try:
            dist = pkg_resources.get_distribution(package)
            installed[package] = f"{package} {dist.version}"
        except pkg_resources.DistributionNotFound:
            missing[package] = description
    
    return missing, installed

def install_dependencies(missing):
    """Install missing dependencies."""
    print(f"Installing {len(missing)} missing dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
    print("Dependencies installed successfully!")

def prompt_install_optional(missing_optional):
    """Prompt user to install optional dependencies."""
    if not missing_optional:
        return
    
    print("\n" + "="*60)
    print("OPTIONAL DEPENDENCIES")
    print("="*60)
    print("The following optional dependencies are missing:")
    for package, description in missing_optional.items():
        print(f"  - {package}: {description}")
    
    print("\nInstallation methods:")
    
    if 'torch' in missing_optional or 'torchaudio' in missing_optional:
        print("\nFor PyTorch:")
        print("  Option 1: pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu")
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            print("  Option 2 (M1/M2 Mac): pip install torch torchaudio")
        print("  For GPU support, visit: https://pytorch.org/get-started/locally/")
    
    if 'demucs' in missing_optional:
        print("\nFor Demucs:")
        print("  Option 1: pip install demucs")
        print("  Option 2: conda install -c conda-forge demucs")
        print("  For more information: https://github.com/facebookresearch/demucs")
    
    print("\nNote: You can also install these dependencies within the application.")
    print("="*60)
    
    choice = input("\nWould you like to install missing optional dependencies now? (y/n): ")
    if choice.lower() == 'y':
        try:
            # Install PyTorch & torchaudio first if needed
            if 'torch' in missing_optional or 'torchaudio' in missing_optional:
                print("\nInstalling PyTorch and torchaudio...")
                cmd = [
                    sys.executable, "-m", "pip", "install", 
                    "torch", "torchaudio"
                ]
                
                # Use specific index for non-M1 Macs and other platforms
                if not (platform.system() == "Darwin" and platform.machine() == "arm64"):
                    cmd.extend(["--index-url", "https://download.pytorch.org/whl/cpu"])
                    
                subprocess.check_call(cmd)
            
            # Install demucs if needed
            if 'demucs' in missing_optional:
                print("\nInstalling Demucs...")
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "demucs"
                ])
            
            print("\nOptional dependencies installed successfully!")
        except Exception as e:
            print(f"\nError installing optional dependencies: {e}")
            print("You can still use the application, but some features may be limited.")
            print("Try installing the dependencies manually using the commands above.")

def main():
    """Run the application."""
    # Check and install dependencies
    missing = check_dependencies()
    if missing:
        print(f"Missing {len(missing)} dependencies: {', '.join(missing)}")
        install_dependencies(missing)
    
    # Check for optional dependencies
    missing_optional, installed_optional = check_optional_dependencies()
    
    if installed_optional:
        print("\nOptional dependencies found:")
        for package, version in installed_optional.items():
            print(f"  - {version}")
            
    if missing_optional:
        prompt_install_optional(missing_optional)
    
    # Run the main application
    print("\nStarting CaptainStems...")
    subprocess.call([sys.executable, "main.py"])

if __name__ == "__main__":
    main() 