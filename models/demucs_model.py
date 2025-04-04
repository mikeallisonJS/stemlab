import os
import subprocess
import tempfile
import shutil
import time
import sys
import mimetypes
from typing import Callable, Optional

class DemucsModel:
    """
    Wrapper for Demucs models from Facebook Research.
    https://github.com/facebookresearch/demucs
    """
    
    # Formats explicitly supported by Demucs
    SUPPORTED_FORMATS = ['.mp3', '.wav', '.flac', '.ogg']
    
    # Available Demucs models
    AVAILABLE_MODELS = {
        # Demucs v3 models
        "demucs": "Original Demucs v3 model",
        "demucs_extra": "Demucs v3 with extra training",
        "demucs_quantized": "Smaller Demucs v3 model",
        "tasnet": "Conv-TasNet model",
        "tasnet_extra": "Conv-TasNet with extra training",
        
        # Demucs v4 models
        "htdemucs": "Hybrid Transformer Demucs v4 (default)",
        "htdemucs_ft": "Hybrid Transformer Demucs v4 fine-tuned",
        "htdemucs_6s": "Hybrid Transformer Demucs v4 for 6 sources separation"
    }
    
    # Default separation stems for different model types
    SEPARATION_MODES = {
        "v3": ["drums", "bass", "other", "vocals"],
        "v4_standard": ["drums", "bass", "other", "vocals"],
        "v4_6stem": ["drums", "bass", "other", "vocals", "piano", "guitar"]
    }
    
    def __init__(self, model_name="htdemucs"):
        """
        Initialize Demucs model wrapper.
        
        Args:
            model_name: Name of the Demucs model to use
        """
        self.name = f"Demucs ({model_name})"
        self.model_name = model_name
        self.available = self.check_dependencies()
        self.device = "cpu"  # Default to CPU
        
        # Determine if this is a v3 or v4 model
        self.is_v3 = model_name in ["demucs", "demucs_extra", "demucs_quantized", "tasnet", "tasnet_extra"]
        self.is_6stem = model_name == "htdemucs_6s"
        
        # Set separation mode based on model type
        if self.is_v3:
            self.separation_mode = "v3"
        elif self.is_6stem:
            self.separation_mode = "v4_6stem"
        else:
            self.separation_mode = "v4_standard"
            
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
        """Check if demucs is installed."""
        try:
            import demucs
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
        """Install demucs and its dependencies."""
        print("Attempting to install Demucs...")
        
        # First, ensure torch and torchaudio are installed
        try:
            # Try installing torch first
            print("Installing PyTorch dependencies...")
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
            
            # Now try installing demucs
            print("Installing Demucs...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "demucs==4.0.1"
            ])
            
            # Also install ffmpeg-python for format conversion
            print("Installing ffmpeg-python...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "ffmpeg-python"
            ])
            
            # Verify installation
            import demucs
            print(f"Demucs installed successfully: {demucs.__version__}")
            return True
            
        except Exception as e:
            print(f"Error installing Demucs: {e}")
            print("\nAlternative installation options:")
            print("1. Install manually with: pip install torch==2.0.1 torchaudio==2.0.2 demucs==4.0.1 ffmpeg-python")
            print("2. Try installing with conda: conda install -c conda-forge demucs=4.0.1")
            print("3. Visit https://github.com/facebookresearch/demucs for installation instructions")
            return False
    
    def needs_conversion(self, file_path):
        """Check if audio file needs conversion for Demucs compatibility."""
        ext = os.path.splitext(file_path)[1].lower()
        return ext not in self.SUPPORTED_FORMATS
    
    def convert_audio(self, input_file, temp_dir):
        """
        Convert audio file to WAV format for Demucs compatibility.
        
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
        Get a dictionary of available Demucs models.
        
        Returns:
            dict: Model name -> description
        """
        return cls.AVAILABLE_MODELS
    
    def get_model_cmd_args(self, two_stems=False):
        """
        Get the command-line arguments for the selected model.
        
        Args:
            two_stems: Whether to separate into just vocals and instrumental
            
        Returns:
            list: Command-line arguments for Demucs
        """
        cmd_args = []
        
        # Add model name argument
        if self.is_v3:
            cmd_args.extend(["-n", self.model_name])
        else:
            cmd_args.extend(["-n", self.model_name])
            
        # Add two-stems option if requested (only for v4)
        if two_stems and not self.is_v3:
            cmd_args.append("--two-stems=vocals")
        
        return cmd_args
    
    def process(
        self, 
        input_file: str, 
        output_dir: str, 
        two_stems: bool = False,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> str:
        """
        Process audio file and separate it into stems.
        
        Args:
            input_file: Path to audio file
            output_dir: Directory to save separated stems
            two_stems: Whether to separate into just vocals and instrumental 
                      (only for v4 models)
            progress_callback: Function to call with progress updates (0-100)
            
        Returns:
            Path to the directory with separated stems
        """
        # Check if demucs is available
        if not self.available:
            # Try to install demucs
            install_success = self.install_dependencies()
            if not install_success:
                raise ImportError(
                    "Demucs is not installed and could not be installed automatically.\n"
                    "Please install it manually with one of these methods:\n"
                    "- pip install \"numpy>=1.24.0,<2.0.0\" torch==2.0.1 torchaudio==2.0.2 demucs==4.0.1\n"
                    "- conda install -c conda-forge demucs=4.0.1"
                )
            self.available = True
        
        # Validate two_stems option (only for v4 models)
        if two_stems and self.is_v3:
            print("Warning: two_stems option is only supported for v4 models. Ignoring.")
            two_stems = False
            
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
            model_args = self.get_model_cmd_args(two_stems)
                
            # Prepare command
            # We're using subprocess to call the demucs command line tool
            # This gives us better compatibility than using the Python API directly
            cmd = [
                sys.executable, "-m", "demucs.separate",
            ] + model_args + [
                "-d", self.device,
                "--mp3",  # Output as MP3
                "-o", temp_dir,
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
                    # This is not ideal but demucs doesn't provide progress info
                    elapsed = time.time() - start_time
                    # Assume process takes about 30 seconds per minute of audio
                    # This is just a rough estimate
                    progress = min(95, int(10 + (elapsed / 30 * 85)))  # 10% - 95%
                    if progress_callback:
                        progress_callback(progress)
                    time.sleep(0.5)
            
            # Check if process was successful
            if process.returncode != 0:
                error_output = "\n".join(output_lines[-10:]) if output_lines else "No output captured"
                raise Exception(f"Demucs processing failed with return code {process.returncode}\n\nOutput:\n{error_output}")
            
            # Get output directory (Demucs creates a subdirectory with model name)
            # V3 and V4 have slightly different output directory structures
            if self.is_v3:
                model_dir = os.path.join(temp_dir, self.model_name)
            else:
                model_dir = os.path.join(temp_dir, self.model_name.replace("_", "/"))
            
            # Get the track name (directory for this specific track)
            if not os.path.isdir(model_dir):
                raise Exception("Demucs processing failed to create output directory")
                
            track_dirs = os.listdir(model_dir)
            if not track_dirs:
                raise Exception("No tracks were processed")
                
            track_dir = os.path.join(model_dir, track_dirs[0])
            
            # Create output directory
            track_name = os.path.splitext(os.path.basename(input_file))[0]
            final_output_dir = os.path.join(output_dir, f"{track_name}_{self.model_name}_stems")
            os.makedirs(final_output_dir, exist_ok=True)
            
            # Copy stems to output directory
            for stem_file in os.listdir(track_dir):
                src = os.path.join(track_dir, stem_file)
                dst = os.path.join(final_output_dir, stem_file)
                shutil.copy2(src, dst)
            
            return final_output_dir 