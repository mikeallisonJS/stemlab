import os
import subprocess
import tempfile
import shutil
import time
import sys
import mimetypes
import platform
from typing import Callable, Optional, Dict

from models.base_model import BaseModel

class SpleeterModel(BaseModel):
    """
    Wrapper for Spleeter model from Deezer Research.
    https://github.com/deezer/spleeter
    """
    
    # Formats explicitly supported by Spleeter
    SUPPORTED_FORMATS = ['.mp3', '.wav', '.flac', '.ogg']
    
    # Available Spleeter models
    AVAILABLE_MODELS = {
        "2stems": "Vocals and accompaniment separation",
        "4stems": "Vocals, drums, bass, and other separation",
        "5stems": "Vocals, drums, bass, piano, and other separation"
    }
    
    # Default separation stems for different model types
    SEPARATION_MODES = {
        "2stems": ["vocals", "accompaniment"],
        "4stems": ["vocals", "drums", "bass", "other"],
        "5stems": ["vocals", "drums", "bass", "piano", "other"]
    }
    
    def __init__(self, model_name="2stems"):
        """
        Initialize Spleeter model wrapper.
        
        Args:
            model_name: Name of the Spleeter model to use (2stems, 4stems, 5stems)
        """
        self.name = f"Spleeter ({model_name})"
        self.model_name = model_name
        self.available = False  # Will be updated after dependency check
        
        # Detect if we're on Apple Silicon Mac
        self.is_apple_silicon = (
            platform.system() == "Darwin" and 
            platform.machine() == "arm64"
        )
        
        # Specify the dependencies for uninstallation based on platform
        if self.is_apple_silicon:
            self.dependencies = [
                "spleeter",
                "tensorflow-macos",
                "tensorflow-metal",
                "ffmpeg-python",
                "numpy"
            ]
        else:
            self.dependencies = [
                "spleeter",
                "tensorflow",
                "ffmpeg-python",
                "numpy"
            ]
        
        # Set device based on platform
        self.device = "cpu"  # Default device
        self.has_metal = False  # Will be updated during dependency check
        
        # Set separation mode based on model type
        if model_name in self.SEPARATION_MODES:
            self.separation_mode = model_name
        else:
            # Default to 2stems if model name is invalid
            self.separation_mode = "2stems"
        
        # Initialize mimetypes
        if not mimetypes.inited:
            mimetypes.init()
            
        # Check for dependencies and configure devices
        self.available = self.check_dependencies()
        
        # If available, check for Metal acceleration on Apple Silicon
        if self.available and self.is_apple_silicon:
            self.check_metal_acceleration()
        
    def check_dependencies(self):
        """Check if spleeter is installed."""
        try:
            import spleeter
            return True
        except ImportError:
            return False
    
    def check_ffmpeg(self):
        """Check if ffmpeg is installed."""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def install_dependencies(self):
        """Install spleeter and its dependencies."""
        print("Attempting to install Spleeter...")
        
        try:
            # First, ensure numpy 1.x is installed (to prevent issues with 2.x)
            print("Installing NumPy 1.x (for compatibility)...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "numpy>=1.24.0,<2.0.0"
            ])
            
            # Detect if we're on Apple Silicon Mac
            is_apple_silicon = (
                platform.system() == "Darwin" and 
                platform.machine() == "arm64"
            )
            
            # Now install TensorFlow based on the platform
            if is_apple_silicon:
                print("Detected Apple Silicon Mac, installing TensorFlow with Metal support...")
                
                # First, install tensorflow-macos which is compatible with ARM architecture
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", 
                    "tensorflow-macos==2.12.0"
                ])
                
                # Then install tensorflow-metal for GPU acceleration
                try:
                    subprocess.check_call([
                        sys.executable, "-m", "pip", "install", 
                        "tensorflow-metal>=0.7.0"
                    ])
                    print("TensorFlow Metal GPU acceleration installed successfully")
                except Exception as e:
                    print(f"Warning: Could not install tensorflow-metal: {e}")
                    print("Continuing with CPU-only acceleration")
                    
                # Verify we're using the correct version
                print("Verifying TensorFlow installation...")
                import tensorflow as tf
                print(f"Installed TensorFlow version: {tf.__version__}")
                
                # Check for Metal device
                try:
                    physical_devices = tf.config.list_physical_devices()
                    print(f"Available devices: {physical_devices}")
                    
                    metal_available = any("METAL" in str(d).upper() for d in physical_devices)
                    if metal_available:
                        print("Metal GPU acceleration is available for Spleeter")
                    else:
                        print("Metal GPU device not found, will use CPU")
                except Exception as e:
                    print(f"Error checking devices: {e}")
                
            else:
                # Install regular TensorFlow for other platforms
                print("Installing TensorFlow...")
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", 
                    "tensorflow==2.12.0"
                ])
            
            # Install Spleeter
            print("Installing Spleeter...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "spleeter==2.4.0"
            ])
            
            # Also install ffmpeg-python for format conversion
            print("Installing ffmpeg-python...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "ffmpeg-python"
            ])
            
            # Verify installation
            import spleeter
            print(f"Spleeter installed successfully")
            
            return True
            
        except Exception as e:
            print(f"Error installing Spleeter: {e}")
            print("\nAlternative installation options:")
            if platform.system() == "Darwin" and platform.machine() == "arm64":
                print("1. Try using our unified script:")
                print("   python captain.py --install-model spleeter")
                print("2. Install manually with:")
                print("   pip install numpy<2.0.0 tensorflow-macos==2.12.0 tensorflow-metal spleeter==2.4.0 ffmpeg-python")
            else:
                print("1. Try using our unified script:")
                print("   python captain.py --install-model spleeter")
                print("2. Install manually with:")
                print("   pip install numpy<2.0.0 tensorflow==2.12.0 spleeter==2.4.0 ffmpeg-python")
                
            print("3. Try installing with conda: conda install -c conda-forge spleeter ffmpeg-python")
            print("4. Visit https://github.com/deezer/spleeter for installation instructions")
            return False
    
    def needs_conversion(self, file_path):
        """Check if audio file needs conversion for Spleeter compatibility."""
        ext = os.path.splitext(file_path)[1].lower()
        return ext not in self.SUPPORTED_FORMATS
    
    def convert_audio(self, input_file, temp_dir):
        """
        Convert audio file to WAV format for Spleeter compatibility.
        
        Args:
            input_file: Path to input audio file
            temp_dir: Temporary directory to store converted file
            
        Returns:
            Path to converted file, or original file if conversion not needed
        """
        if not self.needs_conversion(input_file):
            return input_file
            
        # Check if ffmpeg is available
        if not self.check_ffmpeg():
            print("Warning: ffmpeg not found, trying to process original file")
            return input_file
            
        # Generate output path in temp directory
        filename = os.path.basename(input_file)
        basename = os.path.splitext(filename)[0]
        converted_file = os.path.join(temp_dir, f"{basename}.wav")
        
        print(f"Converting {input_file} to WAV format...")
        try:
            # Use ffmpeg to convert the file
            result = subprocess.run([
                'ffmpeg', 
                '-i', input_file, 
                '-ar', '44100',  # 44.1kHz sample rate
                '-ac', '2',      # stereo
                '-y',            # overwrite output file
                converted_file
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if result.returncode == 0 and os.path.exists(converted_file):
                print(f"Conversion successful: {converted_file}")
                return converted_file
            else:
                print(f"Conversion failed, using original file")
                return input_file
                
        except Exception as e:
            print(f"Error during conversion: {e}")
            return input_file
    
    @classmethod
    def get_available_models(cls) -> Dict[str, str]:
        """
        Get a dictionary of available Spleeter models.
        
        Returns:
            dict: Model name -> description
        """
        return cls.AVAILABLE_MODELS
    
    def get_model_cmd_args(self):
        """
        Get the command-line arguments for the selected model.
        
        Returns:
            list: Command-line arguments for Spleeter
        """
        # Determine the stems value from the model name
        stems = self.model_name[0] if self.model_name[0].isdigit() else "2"
        
        cmd_args = [
            "separate",
            "-p",
            f"spleeter:{stems}stems",
        ]
        
        return cmd_args
    
    def process(
        self, 
        input_file: str, 
        output_dir: str, 
        two_stems: bool = False,  # Ignored for Spleeter, kept for API compatibility
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> str:
        """
        Process an audio file using Spleeter.
        
        Args:
            input_file: Path to input audio file
            output_dir: Path to output directory
            two_stems: Ignored for Spleeter (kept for API compatibility)
            progress_callback: Function to call with progress updates (0-100)
            
        Returns:
            Path to directory containing separated stems
        """
        if not self.available:
            if progress_callback:
                progress_callback(0)
            print("Spleeter is not installed. Please install it first.")
            if progress_callback:
                progress_callback(100)
            return None
            
        if progress_callback:
            progress_callback(5)
            
        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Check if we need to convert the audio file
            if self.needs_conversion(input_file):
                if progress_callback:
                    progress_callback(10)
                input_file = self.convert_audio(input_file, temp_dir)
            else:
                if progress_callback:
                    progress_callback(15)
                
            # Create the final output directory
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
                
            if progress_callback:
                progress_callback(20)
                
            # Get base filename without extension
            filename = os.path.basename(input_file)
            basename = os.path.splitext(filename)[0]
            
            # Create separator arguments
            args = self.get_model_cmd_args()
            
            # Set up environment variables for platform-specific optimizations
            env = os.environ.copy()
            
            # For Apple Silicon Macs with Metal support
            if self.is_apple_silicon:
                if self.has_metal:
                    print("Using Metal GPU acceleration for Spleeter")
                    # These environment variables help ensure proper Metal GPU usage
                    env["TF_FORCE_GPU_ALLOW_GROWTH"] = "true"
                    env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
                    env["XLA_FLAGS"] = "--xla_gpu_cuda_data_dir=/usr/local"
                else:
                    print("Apple Silicon detected but Metal acceleration not available. Using CPU.")
            
            # Platform-specific command arguments
            if self.is_apple_silicon:
                # Special handling for Apple Silicon to avoid AVX errors
                cmd = [
                    sys.executable, "-m", "spleeter", "separate",
                    "-p", f"spleeter:{self.separation_mode}",
                    "-o", output_dir,
                    input_file,
                ] + args
            else:
                # Standard command for other platforms
                cmd = [
                    sys.executable, "-m", "spleeter", "separate",
                    "-p", f"spleeter:{self.separation_mode}",
                    "-o", output_dir,
                    input_file,
                ] + args
            
            print(f"Running Spleeter: {' '.join(cmd)}")
                
            if progress_callback:
                progress_callback(30)
                
            # Run the separation process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                env=env
            )
            
            # Monitor progress
            if progress_callback:
                # Since Spleeter doesn't provide progress updates, we'll simulate progress
                for i in range(7):
                    if process.poll() is not None:
                        break
                    progress_value = 30 + i * 10
                    progress_callback(min(90, progress_value))
                    time.sleep(0.5)
            
            # Wait for process to complete
            stdout, stderr = process.communicate()
            
            # Check for errors
            if process.returncode != 0:
                print(f"Error running Spleeter: {stderr}")
                if self.is_apple_silicon and "AVX" in stderr:
                    print("\nERROR: AVX instruction error detected on Apple Silicon.")
                    print("This typically happens when using the wrong TensorFlow package.")
                    print("\nTo fix this issue:")
                    print("1. Run: python captain.py --install-model spleeter")
                    print("   - This will install tensorflow-macos and tensorflow-metal")
                    print("2. Or install manually:")
                    print("   pip uninstall -y tensorflow")
                    print("   pip install tensorflow-macos==2.12.0 tensorflow-metal>=0.7.0")
                return None
                
            if progress_callback:
                progress_callback(95)
                
            # Return the path to the separated stems
            result_path = os.path.join(output_dir, basename)
            
            if progress_callback:
                progress_callback(100)
                
            return result_path
            
        except Exception as e:
            print(f"Error processing audio: {e}")
            return None
        finally:
            # Clean up temporary directory
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Warning: Failed to clean up temp directory: {e}")
    
    def uninstall_dependencies(self) -> bool:
        """
        Uninstall Spleeter and its dependencies with special handling for Apple Silicon.
        
        Returns:
            bool: True if uninstallation was successful, False otherwise
        """
        try:
            print(f"Uninstalling {self.name} dependencies...")
            success_count = 0
            fail_count = 0
            
            # Platform-specific packages with correct versions
            if self.is_apple_silicon:
                packages = [
                    "spleeter==2.4.0",
                    "tensorflow-macos==2.12.0",
                    "tensorflow-metal",
                    "ffmpeg-python",
                    "numpy<2.0.0",
                    "protobuf"  # Often causes issues if not properly removed
                ]
            else:
                packages = [
                    "spleeter==2.4.0",
                    "tensorflow==2.12.0",
                    "ffmpeg-python",
                    "numpy<2.0.0",
                    "protobuf"
                ]
            
            # First try to uninstall the main package
            try:
                print("Removing main package: spleeter")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "uninstall", "-y", "spleeter"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False
                )
                
                if result.returncode == 0:
                    success_count += 1
                    print("Successfully uninstalled spleeter")
                else:
                    print(f"Failed to uninstall spleeter: {result.stderr}")
            except Exception as e:
                print(f"Error uninstalling spleeter: {e}")
            
            # Then try each dependency
            for package in packages:
                if package.startswith("spleeter"):
                    continue  # Already tried to uninstall main package
                    
                package_name = package.split("==")[0].split("<")[0]
                try:
                    print(f"Removing package: {package_name}")
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "uninstall", "-y", package_name],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False
                    )
                    
                    if result.returncode == 0:
                        success_count += 1
                        print(f"Successfully uninstalled {package_name}")
                    else:
                        fail_count += 1
                        print(f"Failed to uninstall {package_name}: {result.stderr}")
                except Exception as e:
                    fail_count += 1
                    print(f"Error uninstalling {package_name}: {e}")
            
            # Special handling for Apple Silicon Macs
            if self.is_apple_silicon:
                print("\nSpecial cleanup for Apple Silicon Macs...")
                
                # Try to remove TensorFlow Metal plugins
                tf_packages = [
                    "tensorflow-plugin-metal",
                    "tensorflow-metal-plugin",
                    "tensorflow-metal",
                    "metal-plugin"
                ]
                
                for pkg in tf_packages:
                    try:
                        subprocess.run(
                            [sys.executable, "-m", "pip", "uninstall", "-y", pkg],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            check=False
                        )
                    except:
                        pass
            
            # Consider the operation successful if we uninstalled at least the main package
            if success_count > 0:
                print(f"Successfully uninstalled {success_count} packages")
                
                # Update availability
                self.available = False
                
                return True
            else:
                print(f"Failed to uninstall any packages")
                return False
            
        except Exception as e:
            print(f"Error during dependency uninstallation: {e}")
            return False 

    def check_metal_acceleration(self):
        """Check for Metal GPU acceleration on Apple Silicon."""
        try:
            import tensorflow as tf
            
            print(f"TensorFlow version: {tf.__version__}")
            
            # Check for Metal devices
            physical_devices = tf.config.list_physical_devices()
            metal_devices = [d for d in physical_devices if "METAL" in str(d).upper()]
            
            if metal_devices:
                print(f"Metal GPU acceleration is available: {metal_devices}")
                self.device = "metal"
                self.has_metal = True
            else:
                print("Metal GPU acceleration not found, using CPU")
                self.device = "cpu"
                self.has_metal = False
                
            # Configure TensorFlow to use Metal if available
            if self.has_metal:
                try:
                    # Allow memory growth to avoid allocating all GPU memory at once
                    for device in metal_devices:
                        tf.config.experimental.set_memory_growth(device, True)
                    print("Configured Metal device for memory growth")
                except Exception as e:
                    print(f"Error configuring Metal device: {e}")
            
        except (ImportError, AttributeError) as e:
            print(f"Error checking for Metal acceleration: {e}")
            self.device = "cpu"
            self.has_metal = False 