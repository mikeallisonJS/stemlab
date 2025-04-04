import os
import subprocess
import tempfile
import shutil
import time
import sys
import mimetypes
from typing import Callable, Optional

class SpleeterModel:
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
        self.available = self.check_dependencies()
        self.device = "cpu"  # Spleeter CPU/GPU is managed through Tensorflow
        
        # Set separation mode based on model type
        if model_name in self.SEPARATION_MODES:
            self.separation_mode = model_name
        else:
            # Default to 2stems if model name is invalid
            self.separation_mode = "2stems"
        
        # Initialize mimetypes
        if not mimetypes.inited:
            mimetypes.init()
        
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
            
            # Now install TensorFlow CPU (2.12.x series is stable with Spleeter)
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
            print("1. Install manually with: pip install numpy<2.0.0 tensorflow==2.12.0 spleeter==2.4.0 ffmpeg-python")
            print("2. Try installing with conda: conda install -c conda-forge spleeter ffmpeg-python")
            print("3. Visit https://github.com/deezer/spleeter for installation instructions")
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
    def get_available_models(cls):
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
        Process audio file and separate it into stems.
        
        Args:
            input_file: Path to audio file
            output_dir: Directory to save separated stems
            two_stems: Not used for Spleeter, kept for API compatibility
            progress_callback: Function to call with progress updates (0-100)
            
        Returns:
            Path to the directory with separated stems
        """
        # Check if spleeter is installed
        if not self.available:
            # Try to install spleeter
            install_success = self.install_dependencies()
            if not install_success:
                raise ImportError(
                    "Spleeter is not installed and could not be installed automatically.\n"
                    "Please install it manually with one of these methods:\n"
                    "- pip install numpy<2.0.0 tensorflow==2.12.0 spleeter==2.4.0\n"
                    "- conda install -c conda-forge spleeter"
                )
            self.available = True
            
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Convert audio if needed
            if self.needs_conversion(input_file):
                if progress_callback:
                    progress_callback(5)
                processed_input = self.convert_audio(input_file, temp_dir)
            else:
                processed_input = input_file
            
            if progress_callback:
                progress_callback(10)
                
            # Get model-specific command arguments
            model_args = self.get_model_cmd_args()
            
            # Create output directory path inside temp_dir
            spleeter_output_dir = os.path.join(temp_dir, "output")
            
            # Determine the stems value from the model name
            stems = self.model_name[0] if self.model_name[0].isdigit() else "2"
                
            # Prepare command
            # We're using subprocess to call the spleeter command line tool
            cmd = [
                sys.executable, "-m", "spleeter",
            ] + model_args + [
                "-o", spleeter_output_dir,
                processed_input
            ]
            
            # Run the process
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            
            # Track progress
            if progress_callback and processed_input == input_file:
                # No conversion happened, start from 0
                progress_callback(0)
                
            # Monitor the process
            completed = False
            start_time = time.time()
            output_lines = []
            
            while not completed:
                if process.poll() is not None:
                    completed = True
                    if progress_callback:
                        progress_callback(100)
                else:
                    # Read output line (if available)
                    if process.stdout:
                        line = process.stdout.readline()
                        if line:
                            output_lines.append(line.strip())
                            print(line.strip())  # Echo to console
                    
                    # Add arbitrary progress based on elapsed time
                    # This is not ideal but spleeter doesn't provide progress info
                    elapsed = time.time() - start_time
                    # Assume process takes about 20 seconds per minute of audio
                    # This is just a rough estimate
                    progress = min(95, int(10 + (elapsed / 20 * 85)))  # 10% - 95%
                    if progress_callback:
                        progress_callback(progress)
                    time.sleep(0.5)
            
            # Check if process was successful
            if process.returncode != 0:
                error_output = "\n".join(output_lines[-10:]) if output_lines else "No output captured"
                raise Exception(f"Spleeter processing failed with return code {process.returncode}\n\nOutput:\n{error_output}")
            
            # Get the track name from the input file
            track_name = os.path.splitext(os.path.basename(processed_input))[0]
            
            # Spleeter creates a directory with the name of the track in the output dir
            spleeter_track_dir = os.path.join(spleeter_output_dir, track_name)
            
            if not os.path.isdir(spleeter_track_dir):
                raise Exception("Spleeter processing failed to create output directory")
            
            # Create final output directory
            final_output_dir = os.path.join(output_dir, f"{track_name}_spleeter_{stems}stems")
            os.makedirs(final_output_dir, exist_ok=True)
            
            # Copy stems to output directory
            for stem_file in os.listdir(spleeter_track_dir):
                src = os.path.join(spleeter_track_dir, stem_file)
                dst = os.path.join(final_output_dir, stem_file)
                shutil.copy2(src, dst)
            
            return final_output_dir 