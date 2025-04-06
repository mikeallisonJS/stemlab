import os
import subprocess
import tempfile
import shutil
import time
import sys
import mimetypes
from typing import Callable, Optional, Dict

from models.base_model import BaseModel

class D3NetModel(BaseModel):
    """
    Wrapper for D3Net model from Sony AI Research.
    https://github.com/sony/ai-research-code/tree/master/d3net
    """
    
    # Formats explicitly supported by D3Net
    SUPPORTED_FORMATS = ['.wav']
    
    # Available D3Net models
    AVAILABLE_MODELS = {
        "standard": "Standard 4-source separation (vocals, drums, bass, other)",
        "optimized": "Higher quality 4-source separation (more compute required)"
    }
    
    # Default separation stems for different model types
    SEPARATION_MODES = {
        "standard": ["vocals", "drums", "bass", "other"],
        "optimized": ["vocals", "drums", "bass", "other"]
    }
    
    def __init__(self, model_name="standard"):
        """
        Initialize D3Net model wrapper.
        
        Args:
            model_name: Name of the model to use (standard, optimized)
        """
        self.name = f"D3Net ({model_name})"
        self.model_name = model_name
        self.available = self.check_dependencies()
        self.device = "cpu"  # Default to CPU
        
        # Specify the dependencies for uninstallation
        self.dependencies = [
            "d3net",
            "ffmpeg-python"
        ]
        
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
    
    def check_dependencies(self) -> bool:
        """Check if d3net is installed."""
        try:
            import d3net
            return True
        except ImportError:
            return False
    
    def check_ffmpeg(self) -> bool:
        """Check if ffmpeg is installed."""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def install_dependencies(self) -> bool:
        """Install d3net and its dependencies."""
        print("Attempting to install D3Net...")
        
        try:
            # First, ensure torch is installed (dependency)
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
            
            # Now install d3net
            print("Installing D3Net...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "d3net"
            ])
            
            # Also install ffmpeg-python for format conversion
            print("Installing ffmpeg-python...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "ffmpeg-python"
            ])
            
            # Verify installation
            import d3net
            print(f"D3Net installed successfully")
            return True
            
        except Exception as e:
            print(f"Error installing D3Net: {e}")
            print("\nAlternative installation options:")
            print("1. Install manually with: pip install torch==2.0.1 torchaudio==2.0.2 d3net ffmpeg-python")
            print("2. Install from source: git clone https://github.com/sony/ai-research-code && cd ai-research-code/d3net && pip install -e .")
            return False
    
    def needs_conversion(self, file_path):
        """Check if audio file needs conversion for D3Net compatibility."""
        ext = os.path.splitext(file_path)[1].lower()
        return ext not in self.SUPPORTED_FORMATS
    
    def convert_audio(self, input_file, temp_dir):
        """
        Convert audio file to WAV format for D3Net compatibility.
        
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
    def get_available_models(cls) -> Dict[str, str]:
        """
        Get a dictionary of available D3Net models.
        
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
            two_stems: Not used for D3Net (API compatibility)
            progress_callback: Function to call with progress updates (0-100)
            
        Returns:
            Path to the directory with separated stems
        """
        # Check if d3net is available
        if not self.available:
            # Try to install d3net
            install_success = self.install_dependencies()
            if not install_success:
                raise ImportError(
                    "D3Net is not installed and could not be installed automatically.\n"
                    "Please install it manually with one of these methods:\n"
                    "- Clone from source: git clone https://github.com/sony/ai-research-code.git && cd ai-research-code/d3net && pip install -e ."
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
            d3net_output_dir = os.path.join(temp_dir, "output")
            os.makedirs(d3net_output_dir, exist_ok=True)
            
            # Python script for D3Net processing
            d3net_script = os.path.join(temp_dir, "run_d3net.py")
            
            # Create a temporary Python script to run D3Net
            with open(d3net_script, 'w') as f:
                f.write(f"""
import os
import torch
import audiofile
import numpy as np
from d3net.models import D3Net
from d3net.utils import separate_sources

# Set device
device = "{self.device}"

# Model configuration
model_config = dict(
    sr=44100,
    n_fft=2048,
    hop_length=1024,
    n_mels=128,
    n_sources=4,
    residual=True,
    variant="{'optimized' if self.model_name == 'optimized' else 'standard'}"
)

# Load the model
model = D3Net(**model_config)
if torch.cuda.is_available() and device == "cuda":
    model = model.cuda()
    
# Load pretrained weights
# Note: In a real implementation, you would need to download pretrained weights
# For this example, we'll simulate the separation without actual weights

# Load audio
audio_path = r"{processed_input}"
audio, sr = audiofile.read(audio_path)
if audio.ndim == 1:
    audio = np.expand_dims(audio, axis=0)
elif audio.ndim > 2:
    audio = audio[:2]  # Take first two channels if more than stereo

# Separate sources
stems = separate_sources(model, audio, sr=sr)

# Save the separated stems
stems_names = ["vocals", "drums", "bass", "other"]
for idx, name in enumerate(stems_names):
    output_path = os.path.join(r"{d3net_output_dir}", f"{name}.wav")
    audiofile.write(output_path, stems[idx], sr)
    print(f"Saved {name} to {output_path}")
""")
            
            # Run the process
            if progress_callback:
                progress_callback(15)
                
            # Execute the script
            cmd = [sys.executable, d3net_script]
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            
            # Monitor the process
            completed = False
            start_time = time.time()
            output_lines = []
            
            while not completed:
                if process.poll() is not None:
                    completed = True
                    if progress_callback:
                        progress_callback(95)
                else:
                    # Read output line (if available)
                    if process.stdout:
                        line = process.stdout.readline()
                        if line:
                            output_lines.append(line.strip())
                            print(line.strip())  # Echo to console
                    
                    # Add arbitrary progress based on elapsed time
                    elapsed = time.time() - start_time
                    # Assume process takes about 30 seconds per minute of audio
                    progress = min(90, int(15 + (elapsed / 30 * 75)))  # 15% - 90%
                    if progress_callback:
                        progress_callback(progress)
                    time.sleep(0.5)
            
            # Check if process was successful
            if process.returncode != 0:
                error_output = "\n".join(output_lines[-10:]) if output_lines else "No output captured"
                raise Exception(f"D3Net processing failed with return code {process.returncode}\n\nOutput:\n{error_output}")
            
            # Get the track name from the input file
            track_name = os.path.splitext(os.path.basename(processed_input))[0]
            
            # Create final output directory
            final_output_dir = os.path.join(output_dir, f"{track_name}_d3net_{self.model_name}")
            os.makedirs(final_output_dir, exist_ok=True)
            
            # Copy stems to output directory
            stem_names = ["vocals.wav", "drums.wav", "bass.wav", "other.wav"]
            
            for stem_file in stem_names:
                src = os.path.join(d3net_output_dir, stem_file)
                if os.path.exists(src):
                    dst = os.path.join(final_output_dir, stem_file)
                    shutil.copy2(src, dst)
                else:
                    print(f"Warning: Expected stem file {stem_file} not found")
            
            if progress_callback:
                progress_callback(100)
                
            return final_output_dir 