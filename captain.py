#!/usr/bin/env python3
"""
CaptainStems - Unified Entrypoint Script

This script serves as the single entrypoint for CaptainStems, handling:
1. Dependency management for all models
2. Platform-specific setup (especially Apple Silicon)
3. Application launching
4. Model installation

Usage:
  python captain.py                    # Run the application with dependency checks
  python captain.py --setup            # Setup/install dependencies only
  python captain.py --install-model X  # Install a specific model (demucs, spleeter, etc.)
"""

import os
import sys
import subprocess
import platform
import argparse
import time
import shutil
from typing import Dict, List, Optional, Tuple, Set

# Define colors for terminal output
class Colors:
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color

def print_header(title: str) -> None:
    """Print a formatted header."""
    print(f"\n{Colors.BLUE}{Colors.BOLD}{'=' * 60}{Colors.NC}")
    print(f"{Colors.BLUE}{Colors.BOLD}{title}{Colors.NC}")
    print(f"{Colors.BLUE}{Colors.BOLD}{'=' * 60}{Colors.NC}")

def print_success(msg: str) -> None:
    """Print a success message."""
    print(f"{Colors.GREEN}✓ {msg}{Colors.NC}")

def print_warning(msg: str) -> None:
    """Print a warning message."""
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.NC}")

def print_error(msg: str) -> None:
    """Print an error message."""
    print(f"{Colors.RED}✗ {msg}{Colors.NC}")

def print_step(msg: str) -> None:
    """Print a step message."""
    print(f"{Colors.BOLD}→ {msg}{Colors.NC}")

# Platform detection
IS_MACOS = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows" or platform.system().startswith("MINGW")
IS_LINUX = platform.system() == "Linux"
IS_APPLE_SILICON = IS_MACOS and platform.machine() == "arm64"

# Check Python version
PYTHON_VERSION = platform.python_version_tuple()
PYTHON_VERSION_STR = '.'.join(PYTHON_VERSION)
IS_PYTHON_310_COMPATIBLE = (
    int(PYTHON_VERSION[0]) == 3 and
    int(PYTHON_VERSION[1]) >= 10
)

def check_python_compatibility() -> bool:
    """Check Python version compatibility and print appropriate messages."""
    if not IS_PYTHON_310_COMPATIBLE:
        print_warning(f"Detected Python {PYTHON_VERSION_STR}")
        print_warning("CaptainStems works best with Python 3.10 or newer.")
        
        if int(PYTHON_VERSION[1]) >= 12:
            print_error("Python 3.12+ has known compatibility issues with AI model libraries.")
            print_warning("Consider using Python 3.10 for best compatibility.")
            
        return False
    
    print_success(f"Python {PYTHON_VERSION_STR} detected")
    return True

# Package management utilities
def check_package_installed(package_name: str) -> Tuple[bool, Optional[str]]:
    """
    Check if a package is installed and return its version.
    
    Args:
        package_name: Name of the package to check
        
    Returns:
        Tuple of (is_installed, version)
    """
    try:
        import pkg_resources
        try:
            package = pkg_resources.get_distribution(package_name)
            return True, package.version
        except pkg_resources.DistributionNotFound:
            return False, None
    except ImportError:
        print_step("Installing setuptools...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "setuptools"], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import pkg_resources
        try:
            package = pkg_resources.get_distribution(package_name)
            return True, package.version
        except pkg_resources.DistributionNotFound:
            return False, None

def install_package(package_name: str, version: Optional[str] = None) -> bool:
    """
    Install a Python package.
    
    Args:
        package_name: Name of the package to install
        version: Specific version to install
        
    Returns:
        True if installation was successful
    """
    package_spec = package_name
    if version:
        package_spec = f"{package_name}=={version}"
        
    print_step(f"Installing {package_spec}...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_spec],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print_error(f"Failed to install {package_spec}: {result.stderr}")
            return False
        return True
    except Exception as e:
        print_error(f"Error installing {package_spec}: {e}")
        return False

def check_dependencies(requirements_file: str) -> List[str]:
    """
    Check for missing required packages from requirements.txt.
    
    Args:
        requirements_file: Path to requirements.txt
        
    Returns:
        List of missing packages
    """
    try:
        with open(requirements_file) as f:
            requirements = []
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                requirements.append(line)
        
        missing = []
        for requirement in requirements:
            # Parse package name from requirement spec
            package = requirement.split('>=')[0].split('==')[0].split('<')[0].strip()
            if not package:
                continue
                
            installed, _ = check_package_installed(package)
            if not installed:
                missing.append(requirement)
        
        return missing
    except FileNotFoundError:
        print_error(f"Requirements file not found: {requirements_file}")
        return []

def install_core_dependencies() -> bool:
    """
    Install core dependencies from requirements.txt.
    
    Returns:
        True if all dependencies were installed successfully
    """
    missing = check_dependencies('requirements.txt')
    if not missing:
        print_success("All core dependencies are installed")
        return True
    
    print_step(f"Installing {len(missing)} missing core dependencies...")
    for package in missing:
        print_step(f"Installing {package}...")
        if not install_package(package):
            print_error(f"Failed to install {package}")
            return False
    
    print_success("Core dependencies installed successfully")
    return True

# Model-specific dependency management
def install_tensorflow_dependencies() -> bool:
    """
    Install TensorFlow and related dependencies with platform-specific handling.
    
    Returns:
        True if installation was successful
    """
    print_header("Installing TensorFlow Dependencies")
    
    # First ensure NumPy 1.x is installed (TensorFlow requirement)
    print_step("Installing NumPy 1.x (required for TensorFlow)...")
    if not install_package("numpy", "1.24.3"):
        return False
    
    if IS_APPLE_SILICON:
        print_step("Installing TensorFlow for Apple Silicon...")
        
        # Install Apple-specific TensorFlow
        if not install_package("tensorflow-macos", "2.12.0"):
            return False
        
        # Install Metal plugin for GPU acceleration
        print_step("Installing Metal GPU support...")
        if not install_package("tensorflow-metal", "0.8.0"):
            print_warning("Could not install tensorflow-metal. Continuing with CPU-only support.")
        else:
            print_success("Metal GPU acceleration enabled")
            
    else:
        # Standard TensorFlow for other platforms
        print_step("Installing TensorFlow...")
        if not install_package("tensorflow", "2.12.0"):
            return False
    
    # Verify TensorFlow installation
    print_step("Verifying TensorFlow installation...")
    try:
        import tensorflow as tf
        print_success(f"TensorFlow {tf.__version__} installed successfully")
        
        # Check for Metal devices on Apple Silicon
        if IS_APPLE_SILICON:
            try:
                physical_devices = tf.config.list_physical_devices()
                metal_devices = [d for d in physical_devices if "METAL" in str(d).upper()]
                if metal_devices:
                    print_success(f"Metal GPU acceleration available: {metal_devices}")
                else:
                    print_warning("Metal GPU acceleration not detected")
            except Exception as e:
                print_warning(f"Error checking Metal devices: {e}")
                
        return True
        
    except ImportError as e:
        print_error(f"TensorFlow verification failed: {e}")
        return False

def install_pytorch_dependencies() -> bool:
    """
    Install PyTorch and related dependencies with platform-specific handling.
    
    Returns:
        True if installation was successful
    """
    print_header("Installing PyTorch Dependencies")
    
    # First ensure NumPy 1.x is installed
    print_step("Installing NumPy 1.x (required for PyTorch)...")
    if not install_package("numpy", "1.24.3"):
        return False
    
    if IS_APPLE_SILICON:
        # Native PyTorch for Apple Silicon
        print_step("Installing PyTorch for Apple Silicon...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "torch==2.0.1", "torchaudio==2.0.2",
            ])
            print_success("PyTorch installed successfully")
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to install PyTorch: {e}")
            return False
    else:
        # CPU-only PyTorch for other platforms
        print_step("Installing PyTorch (CPU version)...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "torch==2.0.1", "torchaudio==2.0.2",
                "--index-url", "https://download.pytorch.org/whl/cpu"
            ])
            print_success("PyTorch installed successfully")
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to install PyTorch: {e}")
            return False
    
    # Verify PyTorch installation
    print_step("Verifying PyTorch installation...")
    try:
        import torch
        import torchaudio
        
        print_success(f"PyTorch {torch.__version__} installed successfully")
        print_success(f"TorchAudio {torchaudio.__version__} installed successfully")
        
        # Report device availability
        device = "CPU"
        if torch.cuda.is_available():
            device = f"CUDA (GPU): {torch.cuda.get_device_name(0)}"
        elif IS_APPLE_SILICON and torch.backends.mps.is_available():
            device = "Apple Metal (MPS)"
        
        print_success(f"PyTorch will use: {device}")
        return True
        
    except ImportError as e:
        print_error(f"PyTorch verification failed: {e}")
        return False

def install_ffmpeg() -> bool:
    """
    Check for FFmpeg and install if necessary.
    
    Returns:
        True if FFmpeg is available
    """
    # Check if FFmpeg is already installed
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE)
        if result.returncode == 0:
            print_success("FFmpeg is already installed")
            return True
    except FileNotFoundError:
        print_warning("FFmpeg not found")
    
    # Install FFmpeg based on platform
    if IS_MACOS:
        print_step("Installing FFmpeg via Homebrew...")
        try:
            # Check if Homebrew is installed
            brew_result = subprocess.run(['which', 'brew'], 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE)
            if brew_result.returncode != 0:
                print_warning("Homebrew not found. Please install FFmpeg manually:")
                print("  Visit: https://ffmpeg.org/download.html")
                print("  Or install Homebrew (https://brew.sh) and run: brew install ffmpeg")
                return False
            
            # Install FFmpeg using Homebrew
            subprocess.run(['brew', 'install', 'ffmpeg'], check=True)
            print_success("FFmpeg installed successfully")
            return True
        except Exception as e:
            print_error(f"Failed to install FFmpeg: {e}")
            return False
            
    elif IS_LINUX:
        print_step("Installing FFmpeg via package manager...")
        try:
            # Try apt-get (Debian/Ubuntu)
            apt_result = subprocess.run(['which', 'apt-get'], 
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.PIPE)
            if apt_result.returncode == 0:
                subprocess.run(['sudo', 'apt-get', 'update'], check=True)
                subprocess.run(['sudo', 'apt-get', 'install', '-y', 'ffmpeg'], check=True)
                print_success("FFmpeg installed successfully")
                return True
                
            # Try dnf (Fedora)
            dnf_result = subprocess.run(['which', 'dnf'], 
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.PIPE)
            if dnf_result.returncode == 0:
                subprocess.run(['sudo', 'dnf', 'install', '-y', 'ffmpeg'], check=True)
                print_success("FFmpeg installed successfully")
                return True
                
            print_warning("Could not determine package manager. Please install FFmpeg manually:")
            print("  For Ubuntu/Debian: sudo apt-get install ffmpeg")
            print("  For Fedora: sudo dnf install ffmpeg")
            print("  For other distributions: https://ffmpeg.org/download.html")
            return False
            
        except Exception as e:
            print_error(f"Failed to install FFmpeg: {e}")
            return False
    
    else:
        print_warning("Automatic FFmpeg installation not supported on this platform.")
        print("Please install FFmpeg manually:")
        print("  Visit: https://ffmpeg.org/download.html")
        return False

# Model-specific installation functions
def install_demucs(version: int = 4) -> bool:
    """
    Install Demucs and its dependencies.
    
    Args:
        version: Demucs version (3 or 4)
        
    Returns:
        True if installation was successful
    """
    print_header(f"Installing Demucs v{version}")
    
    # Install PyTorch dependencies first
    if not install_pytorch_dependencies():
        print_error("Failed to install PyTorch dependencies for Demucs")
        return False
    
    # Install ffmpeg-python
    print_step("Installing ffmpeg-python...")
    if not install_package("ffmpeg-python"):
        print_warning("Failed to install ffmpeg-python")
    
    # Install Demucs based on version
    if version == 3:
        print_step("Installing Demucs v3...")
        if not install_package("demucs", "3.0.6"):
            print_error("Failed to install Demucs v3")
            return False
    else:
        print_step("Installing Demucs v4...")
        if not install_package("demucs", "4.0.1"):
            print_error("Failed to install Demucs v4")
            return False
    
    print_success(f"Demucs v{version} installed successfully")
    return True

def install_spleeter() -> bool:
    """
    Install Spleeter and its dependencies.
    
    Returns:
        True if installation was successful
    """
    print_header("Installing Spleeter")
    
    # Install TensorFlow dependencies first (platform-specific)
    if not install_tensorflow_dependencies():
        print_error("Failed to install TensorFlow dependencies for Spleeter")
        return False
    
    # Install ffmpeg-python
    print_step("Installing ffmpeg-python...")
    if not install_package("ffmpeg-python"):
        print_warning("Failed to install ffmpeg-python")
    
    # Install Spleeter
    print_step("Installing Spleeter...")
    if not install_package("spleeter", "2.4.0"):
        print_error("Failed to install Spleeter")
        return False
    
    print_success("Spleeter installed successfully")
    return True

def install_bandsplit_rnn() -> bool:
    """
    Install Band-Split RNN and its dependencies.
    
    Returns:
        True if installation was successful
    """
    print_header("Installing Band-Split RNN")
    
    # Install PyTorch dependencies first
    if not install_pytorch_dependencies():
        print_error("Failed to install PyTorch dependencies for Band-Split RNN")
        return False
    
    # Install ffmpeg-python
    print_step("Installing ffmpeg-python...")
    if not install_package("ffmpeg-python"):
        print_warning("Failed to install ffmpeg-python")
    
    # Install Band-Split RNN
    print_step("Installing Band-Split RNN...")
    if not install_package("band-split-rnn"):
        print_error("Failed to install Band-Split RNN")
        return False
    
    print_success("Band-Split RNN installed successfully")
    return True

def install_d3net() -> bool:
    """
    Install D3Net and its dependencies.
    
    Returns:
        True if installation was successful
    """
    print_header("Installing D3Net")
    
    # Install PyTorch dependencies first
    if not install_pytorch_dependencies():
        print_error("Failed to install PyTorch dependencies for D3Net")
        return False
    
    # Install ffmpeg-python
    print_step("Installing ffmpeg-python...")
    if not install_package("ffmpeg-python"):
        print_warning("Failed to install ffmpeg-python")
    
    # Install audiofile
    print_step("Installing audiofile...")
    if not install_package("audiofile"):
        print_warning("Failed to install audiofile")
    
    # Check if D3Net is already installed
    installed, _ = check_package_installed("d3net")
    if installed:
        print_success("D3Net is already installed")
        return True
    
    # Clone and install D3Net from source
    print_step("Installing D3Net from source...")
    try:
        # Create a temporary directory for cloning
        temp_dir = os.path.join(tempfile.gettempdir(), "d3net_install")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Clone the repo
        print_step("Cloning D3Net repository...")
        subprocess.run(
            ["git", "clone", "https://github.com/sony/ai-research-code.git", temp_dir],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        
        # Install D3Net
        print_step("Installing D3Net package...")
        d3net_dir = os.path.join(temp_dir, "d3net")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", d3net_dir],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        print_success("D3Net installed successfully")
        return True
        
    except Exception as e:
        print_error(f"Failed to install D3Net: {e}")
        return False

def run_application() -> int:
    """
    Run the main application.
    
    Returns:
        Exit code from the application
    """
    print_header("Starting CaptainStems")
    
    try:
        # Run the main application
        return subprocess.call([sys.executable, "main.py"])
    except Exception as e:
        print_error(f"Error running application: {e}")
        return 1

def setup_environment() -> bool:
    """
    Set up the environment with core dependencies.
    
    Returns:
        True if setup was successful
    """
    print_header("Setting Up CaptainStems Environment")
    
    # Check Python compatibility
    check_python_compatibility()
    
    # Check/install core dependencies
    if not install_core_dependencies():
        print_error("Failed to install core dependencies")
        return False
    
    # Check for FFmpeg
    if not install_ffmpeg():
        print_warning("FFmpeg installation failed or skipped")
        print_warning("Some audio conversion features may be limited")
    
    print_success("Environment setup complete")
    return True

def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="CaptainStems - Audio Source Separation Tool")
    parser.add_argument("--setup", action="store_true", help="Set up environment only")
    parser.add_argument("--install-model", choices=["demucs", "demucs-v3", "spleeter", "bandsplit", "d3net", "all"],
                      help="Install a specific model")
    parser.add_argument("--check", action="store_true", help="Check dependency status only")
    parser.add_argument("--version", action="store_true", help="Show version information")
    
    args = parser.parse_args()
    
    # Show version information
    if args.version:
        print("CaptainStems - Audio Source Separation Tool")
        print("Version: 1.0.0")
        print(f"Python: {PYTHON_VERSION_STR}")
        print(f"Platform: {platform.system()} {platform.machine()}")
        if IS_APPLE_SILICON:
            print("Apple Silicon detected: Using native acceleration")
        return 0
    
    # Check dependencies only
    if args.check:
        print_header("Checking Dependencies")
        check_python_compatibility()
        
        print_step("Checking core dependencies...")
        missing = check_dependencies('requirements.txt')
        if not missing:
            print_success("All core dependencies are installed")
        else:
            print_warning(f"Missing {len(missing)} core dependencies")
            for package in missing:
                print(f"  - {package}")
        
        # Check model dependencies
        try:
            print_step("Checking model dependencies...")
            
            # Check PyTorch (for Demucs, Band-Split RNN, D3Net)
            pytorch_installed, pytorch_version = check_package_installed("torch")
            if pytorch_installed:
                print_success(f"PyTorch {pytorch_version} is installed")
            else:
                print_warning("PyTorch is not installed")
            
            # Check TensorFlow (for Spleeter)
            tf_installed, tf_version = check_package_installed("tensorflow")
            tf_macos_installed, tf_macos_version = check_package_installed("tensorflow-macos")
            
            if tf_installed:
                print_success(f"TensorFlow {tf_version} is installed")
            elif tf_macos_installed:
                print_success(f"TensorFlow for Mac {tf_macos_version} is installed")
            else:
                print_warning("TensorFlow is not installed")
            
            # Check model packages
            demucs_installed, demucs_version = check_package_installed("demucs")
            spleeter_installed, spleeter_version = check_package_installed("spleeter")
            bandsplit_installed, bandsplit_version = check_package_installed("band-split-rnn")
            d3net_installed, d3net_version = check_package_installed("d3net")
            
            print("\nModel status:")
            if demucs_installed:
                print_success(f"Demucs {demucs_version} is installed")
            else:
                print_warning("Demucs is not installed")
                
            if spleeter_installed:
                print_success(f"Spleeter {spleeter_version} is installed")
            else:
                print_warning("Spleeter is not installed")
                
            if bandsplit_installed:
                print_success(f"Band-Split RNN {bandsplit_version} is installed")
            else:
                print_warning("Band-Split RNN is not installed")
                
            if d3net_installed:
                print_success(f"D3Net {d3net_version} is installed")
            else:
                print_warning("D3Net is not installed")
                
        except Exception as e:
            print_error(f"Error checking model dependencies: {e}")
            
        return 0
    
    # Install a specific model
    if args.install_model:
        # First ensure core dependencies
        if not install_core_dependencies():
            print_error("Failed to install core dependencies")
            return 1
            
        model = args.install_model.lower()
        
        if model == "demucs":
            if not install_demucs(version=4):
                return 1
        elif model == "demucs-v3":
            if not install_demucs(version=3):
                return 1
        elif model == "spleeter":
            if not install_spleeter():
                return 1
        elif model == "bandsplit":
            if not install_bandsplit_rnn():
                return 1
        elif model == "d3net":
            if not install_d3net():
                return 1
        elif model == "all":
            print_header("Installing All Models")
            install_demucs(version=4)
            install_demucs(version=3)
            install_spleeter()
            install_bandsplit_rnn()
            install_d3net()
            print_success("Model installation completed")
            
        return 0
    
    # Setup only
    if args.setup:
        return 0 if setup_environment() else 1
    
    # Run application (default)
    if not setup_environment():
        print_warning("Environment setup incomplete, but attempting to run application...")
    
    return run_application()

if __name__ == "__main__":
    sys.exit(main()) 