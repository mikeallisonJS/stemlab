import os
import subprocess
import tempfile
import shutil
import time
import sys
import mimetypes
from typing import Callable, Optional

class BandSplitRNNModel:
    """
    Wrapper for Band-Split RNN model for audio source separation.
    https://github.com/sevagh/band-split-rnn
    """
    
    # Formats explicitly supported by Band-Split RNN
    SUPPORTED_FORMATS = ['.wav']
    
    # Available Band-Split RNN models
    AVAILABLE_MODELS = {
        "standard": "Standard 4-source separation (vocals, drums, bass, other)",
        "light": "Lightweight 4-source separation (smaller model)"
    }
    
    # Default separation stems for different model types
    SEPARATION_MODES = {
        "standard": ["vocals", "drums", "bass", "other"],
        "light": ["vocals", "drums", "bass", "other"]
    }
    
    def __init__(self, model_name="standard"):
        """
        Initialize Band-Split RNN model wrapper.
        
        Args:
            model_name: Name of the model to use (standard, light)
        """
        self.name = f"Band-Split RNN ({model_name})"
        self.model_name = model_name
        self.available = self.check_dependencies()
        self.device = "cpu"  # Default to CPU
        
        # Set separation mode based on model type
        if model_name in self.SEPARATION_MODES:
            self.separation_mode = model_name
        else:
            # Default to standard if model name is invalid
            self.separation_mode = "standard"
        
        # Try to use CUDA if available
        try:
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            pass
        
        # Initialize mimetypes
        if not mimetypes.inited:
            mimetypes.init()
        
    def check_dependencies(self):
        """Check if band-split-rnn is installed."""
        try:
            import band_split_rnn
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
        """Install band-split-rnn and its dependencies."""
        print("Attempting to install Band-Split RNN...")
        
        try:
            # First, ensure numpy 1.x is installed (to prevent issues with 2.x)
            print("Installing NumPy 1.x (for compatibility)...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "numpy>=1.24.0,<2.0.0"
            ])
            
            # Install PyTorch first (dependency)
            print("Installing PyTorch dependencies...")
            if os.uname().machine == 'arm64' and os.uname().sysname == 'Darwin':
                # M1/M2 Mac - use default PyTorch
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", 
                    "torch==2.0.1", "torchaudio==2.0.2", "--no-deps"
                ])
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", 
                    "torch==2.0.1", "torchaudio==2.0.2"
                ])
            else:
                # CPU-only version for other platforms
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", 
                    "torch==2.0.1", "torchaudio==2.0.2", "--no-deps",
                    "--index-url", "https://download.pytorch.org/whl/cpu"
                ])
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", 
                    "torch==2.0.1", "torchaudio==2.0.2",
                    "--index-url", "https://download.pytorch.org/whl/cpu"
                ])
            
            # Now install band-split-rnn
            print("Installing Band-Split RNN...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "band-split-rnn"
            ])
            
            # Also install ffmpeg-python for format conversion
            print("Installing ffmpeg-python...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "ffmpeg-python"
            ])
            
            # Verify installation
            import band_split_rnn
            print(f"Band-Split RNN installed successfully")
            return True
            
        except Exception as e:
            print(f"Error installing Band-Split RNN: {e}")
            print("\nAlternative installation options:")
            print("1. Install manually with: pip install numpy<2.0.0 torch==2.0.1 torchaudio==2.0.2 band-split-rnn ffmpeg-python")
            print("2. Install from source: git clone https://github.com/sevagh/band-split-rnn && cd band-split-rnn && pip install -e .")
            return False
    
    def needs_conversion(self, file_path):
        """Check if audio file needs conversion for Band-Split RNN compatibility."""
        ext = os.path.splitext(file_path)[1].lower()
        return ext not in self.SUPPORTED_FORMATS
    
    def convert_audio(self, input_file, temp_dir):
        """
        Convert audio file to WAV format for Band-Split RNN compatibility.
        
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
            # Use ffmpeg to convert the file to WAV with appropriate settings
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
        Get a dictionary of available Band-Split RNN models.
        
        Returns:
            dict: Model name -> description
        """
        return cls.AVAILABLE_MODELS
    
    def process(
        self, 
        input_file: str, 
        output_dir: str, 
        two_stems: bool = False,  # Used for API compatibility, not applicable here
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> str:
        """
        Process audio file and separate it into stems.
        
        Args:
            input_file: Path to audio file
            output_dir: Directory to save separated stems
            two_stems: Not used for Band-Split RNN (API compatibility)
            progress_callback: Function to call with progress updates (0-100)
            
        Returns:
            Path to the directory with separated stems
        """
        # Check if band-split-rnn is available
        if not self.available:
            # Try to install band-split-rnn
            install_success = self.install_dependencies()
            if not install_success:
                raise ImportError(
                    "Band-Split RNN is not installed and could not be installed automatically.\n"
                    "Please install it manually with one of these methods:\n"
                    "- pip install numpy<2.0.0 torch==2.0.1 torchaudio==2.0.2 band-split-rnn\n"
                    "- From source: git clone https://github.com/sevagh/band-split-rnn && cd band-split-rnn && pip install -e ."
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
                
            # Create output directory path inside temp_dir
            bandsplit_output_dir = os.path.join(temp_dir, "output")
            os.makedirs(bandsplit_output_dir, exist_ok=True)
            
            # Determine model path based on model type
            model_size = "light" if self.model_name == "light" else "standard"
                
            # Prepare command to run band-split-rnn
            # We're using subprocess to call the band-split-rnn command line tool
            cmd = [
                sys.executable, "-m", "band_split_rnn.inference",
                "--model-size", model_size,
                "--device", self.device,
                "--output-dir", bandsplit_output_dir,
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
                    # This is not ideal but band-split-rnn doesn't provide progress info
                    elapsed = time.time() - start_time
                    # Assume process takes about 25 seconds per minute of audio
                    # This is just a rough estimate
                    progress = min(95, int(10 + (elapsed / 25 * 85)))  # 10% - 95%
                    if progress_callback:
                        progress_callback(progress)
                    time.sleep(0.5)
            
            # Check if process was successful
            if process.returncode != 0:
                error_output = "\n".join(output_lines[-10:]) if output_lines else "No output captured"
                raise Exception(f"Band-Split RNN processing failed with return code {process.returncode}\n\nOutput:\n{error_output}")
            
            # Get the track name from the input file
            track_name = os.path.splitext(os.path.basename(processed_input))[0]
            
            # Create final output directory
            final_output_dir = os.path.join(output_dir, f"{track_name}_bandsplit_{model_size}")
            os.makedirs(final_output_dir, exist_ok=True)
            
            # Copy stems to output directory
            # band-split-rnn creates files like vocals.wav, drums.wav, etc. in the output dir
            stem_names = ["vocals.wav", "drums.wav", "bass.wav", "other.wav"]
            
            for stem_file in stem_names:
                src = os.path.join(bandsplit_output_dir, stem_file)
                if os.path.exists(src):
                    dst = os.path.join(final_output_dir, stem_file)
                    shutil.copy2(src, dst)
                else:
                    print(f"Warning: Expected stem file {stem_file} not found")
            
            return final_output_dir 