#!/usr/bin/env python3

import os
import sys
import subprocess
import platform
import argparse
import tempfile

def main():
    parser = argparse.ArgumentParser(description="Install D3Net and its dependencies")
    parser.add_argument('--model', choices=['standard', 'optimized'], default='standard',
                       help='Model type to install: standard or optimized (default: standard)')
    args = parser.parse_args()

    print("Starting D3Net installation...")
    
    # First, ensure numpy 1.x is installed (to prevent issues with 2.x)
    print("Installing NumPy 1.x for compatibility...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", 
        "numpy>=1.24.0,<2.0.0", "--upgrade", 
        "--no-cache-dir"
    ])
    
    # Install PyTorch first (dependency)
    print("Installing PyTorch dependencies...")
    if platform.system() == 'Darwin' and platform.machine() == 'arm64':
        # M1/M2 Mac - use default PyTorch
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            "torch==2.0.1", "torchaudio==2.0.2", "--no-deps",
            "--no-cache-dir"
        ])
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            "torch==2.0.1", "torchaudio==2.0.2",
            "--no-cache-dir"
        ])
    else:
        # CPU-only version for other platforms
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            "torch==2.0.1", "torchaudio==2.0.2", "--no-deps",
            "--index-url", "https://download.pytorch.org/whl/cpu",
            "--no-cache-dir"
        ])
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            "torch==2.0.1", "torchaudio==2.0.2",
            "--index-url", "https://download.pytorch.org/whl/cpu",
            "--no-cache-dir"
        ])
    
    # Install additional dependencies
    print("Installing audiofile and ffmpeg-python...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", 
        "audiofile", "ffmpeg-python", "--no-cache-dir"
    ])
    
    # Now install D3Net from source
    print("Installing D3Net from source (this may take a while)...")
    try:
        # Create temporary directory for cloning
        with tempfile.TemporaryDirectory() as temp_dir:
            # Clone the repository
            subprocess.check_call([
                "git", "clone", 
                "https://github.com/sony/ai-research-code.git",
                temp_dir
            ])
            
            # Move to the d3net directory
            d3net_dir = os.path.join(temp_dir, "d3net")
            
            # Install the package
            if os.path.exists(d3net_dir):
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "-e", d3net_dir
                ])
            else:
                raise Exception("D3Net directory not found in the repository")
    except subprocess.CalledProcessError as e:
        print(f"Error installing D3Net: {e}")
        print("\nAlternative installation options:")
        print("1. Install manually with: pip install numpy<2.0.0 torch==2.0.1 torchaudio==2.0.2")
        print("2. Install from source: git clone https://github.com/sony/ai-research-code.git && cd ai-research-code/d3net && pip install -e .")
        return 1
    
    # Verify installation
    try:
        import d3net
        print(f"D3Net installed successfully!")
        
        # Print model information
        model_size = args.model
        print(f"Using D3Net model: {model_size}")
        if model_size == "optimized":
            print("Optimized model has better performance but may take more resources")
        else:
            print("Standard model is the default for general purpose separation")
            
        print("\nD3Net will separate audio into the following stems:")
        print("- vocals: Lead and backing vocals")
        print("- drums: Drum kit and percussion")
        print("- bass: Bass guitar and similar instruments")
        print("- other: All other instruments and sounds")
        
        print("\nInstallation complete! You can now use D3Net for audio separation.")
        return 0
    except ImportError as e:
        print(f"Error: D3Net installation verification failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 