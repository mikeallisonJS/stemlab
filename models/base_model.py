import os
import subprocess
import sys
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

class BaseModel(ABC):
    """
    Base class for all audio separation models.
    Defines common interface and utility methods.
    """
    
    @abstractmethod
    def check_dependencies(self) -> bool:
        """Check if all required dependencies are installed."""
        pass
    
    @abstractmethod
    def install_dependencies(self) -> bool:
        """Install all required dependencies."""
        pass
    
    def uninstall_dependencies(self) -> bool:
        """
        Uninstall the model's dependencies.
        
        Returns:
            bool: True if uninstallation was successful, False otherwise
        """
        try:
            if not hasattr(self, 'dependencies'):
                print("No dependencies specified for this model")
                return False
                
            print(f"Uninstalling {self.name} dependencies...")
            success_count = 0
            fail_count = 0
            
            for package in self.dependencies:
                try:
                    print(f"Removing package: {package}")
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "uninstall", "-y", package],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False  # Don't raise exception on non-zero return code
                    )
                    
                    if result.returncode == 0:
                        success_count += 1
                        print(f"Successfully uninstalled {package}")
                    else:
                        fail_count += 1
                        print(f"Failed to uninstall {package}: {result.stderr}")
                except Exception as e:
                    fail_count += 1
                    print(f"Error uninstalling {package}: {e}")
            
            # Consider the operation successful if we uninstalled at least one package
            if success_count > 0:
                print(f"Successfully uninstalled {success_count} out of {len(self.dependencies)} dependencies")
                
                # Update availability
                if hasattr(self, 'available'):
                    self.available = False
                
                return True
            else:
                print(f"Failed to uninstall any dependencies")
                return False
            
        except Exception as e:
            print(f"Error during dependency uninstallation: {e}")
            return False
    
    @classmethod
    @abstractmethod
    def get_available_models(cls) -> Dict[str, str]:
        """
        Get a dictionary of available models.
        
        Returns:
            Dict[str, str]: Model name -> description
        """
        pass
    
    @abstractmethod
    def process(self, input_file: str, output_dir: str, two_stems: bool = False, 
                progress_callback: Optional[callable] = None) -> str:
        """
        Process an audio file and separate it into stems.
        
        Args:
            input_file: Path to audio file
            output_dir: Directory to save separated stems
            two_stems: Whether to separate into just vocals and instrumental
            progress_callback: Function to call with progress updates (0-100)
            
        Returns:
            Path to the directory with separated stems
        """
        pass 