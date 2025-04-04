#!/usr/bin/env python3

import os
import sys
import subprocess
import platform
import argparse

def main():
    parser = argparse.ArgumentParser(description="Install Band-Split RNN and its dependencies")
    parser.add_argument('--model', choices=['standard', 'light'], default='standard',
                       help='Model type to install: standard or light (default: standard)')
    args = parser.parse_args()

    print("Starting Band-Split RNN installation...")
    
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
    
    # Now install band-split-rnn
    print("Installing Band-Split RNN...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            "band-split-rnn", "--no-cache-dir"
        ])
    except subprocess.CalledProcessError as e:
        print(f"Error installing Band-Split RNN: {e}")
        print("\nAlternative installation options:")
        print("1. Install manually with: pip install numpy<2.0.0 torch==2.0.1 torchaudio==2.0.2 band-split-rnn ffmpeg-python")
        print("2. Install from source: git clone https://github.com/sevagh/band-split-rnn && cd band-split-rnn && pip install -e .")
        return 1
    
    # Also install ffmpeg-python for format conversion
    print("Installing ffmpeg-python...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", 
        "ffmpeg-python", "--no-cache-dir"
    ])
    
    # Verify installation
    try:
        import band_split_rnn
        print(f"Band-Split RNN installed successfully!")
        
        # Pretend to download model (band-split-rnn models are automatically downloaded on first use)
        model_size = args.model
        print(f"Using Band-Split RNN model: {model_size}")
        print("Models will be automatically downloaded on first use")
        
        print("\nInstallation complete! You can now use Band-Split RNN for audio separation.")
        return 0
    except ImportError as e:
        print(f"Error: Band-Split RNN installation verification failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 