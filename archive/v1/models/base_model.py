import os
import shutil
import tempfile
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core import ffmpeg, paths
from core.envs import BackendEnv, EnvError
from core.process import ProcessCancelled, run_streaming

ProgressCallback = Optional[Callable[[int], None]]
StatusCallback = Optional[Callable[[str], None]]
LogCallback = Optional[Callable[[str], None]]

RUNNERS_DIR = Path(__file__).resolve().parent / "runners"

# Line prefixes the runner scripts use to report back to the application
PROGRESS_PREFIX = "PROGRESS "
STATUS_PREFIX = "STATUS "


class ModelError(Exception):
    """Raised when a model fails to separate an audio file."""


class ModelNotInstalledError(ModelError):
    """Raised when a model is used before its backend has been installed."""


class BaseModel(ABC):
    """
    Base class for all audio separation models.
    Defines common interface and utility methods.

    Every backend lives in its own isolated Python environment (see
    core.envs), so the models are driven through subprocesses.
    """

    # Key of the environment shared by all variants of a backend
    BACKEND = ""
    # Python versions the backend's packages support, in order of preference
    PYTHON_VERSIONS = ((3, 10), (3, 11))
    # Bump when the packages installed by _install() change
    RECIPE = 1
    # Rough download/disk size shown before installing
    INSTALL_SIZE = ""

    # Model name -> description
    AVAILABLE_MODELS: Dict[str, str] = {}
    # Model name -> stems it produces
    SEPARATION_MODES: Dict[str, List[str]] = {}

    def __init__(self, model_name: str):
        if model_name not in self.AVAILABLE_MODELS:
            raise ValueError(f"Unknown {type(self).__name__} model: {model_name}")
        self.model_name = model_name
        self.name = model_name
        self.env = BackendEnv(self.BACKEND, self.PYTHON_VERSIONS, self.RECIPE)
        self.last_error = ""
        self.available = self.check_dependencies()

    # Installation ---------------------------------------------------------

    def check_dependencies(self) -> bool:
        """Check if all required dependencies are installed."""
        return self.env.is_installed()

    def install_dependencies(self, log: LogCallback = None,
                             cancel_event: Optional[threading.Event] = None) -> bool:
        """
        Install all required dependencies into the backend's environment.

        Args:
            log: Called with each line of installer output
            cancel_event: Set to abort the installation

        Returns:
            bool: True if installation was successful, False otherwise
                  (the reason is kept in ``last_error``)
        """
        self.last_error = ""
        try:
            self.env.create(log, cancel_event)
            paths.weights_dir(self.BACKEND, create=True)
            self._install(log, cancel_event)
            details = self._verify(log, cancel_event)
            self.env.mark_installed(**details)
        except ProcessCancelled:
            self.env.remove()
            self.available = False
            raise
        except Exception as e:
            self.last_error = str(e)
            if log is not None:
                log(f"ERROR: {e}")
            self.env.remove()
            self.available = False
            return False
        self.available = True
        return True

    def uninstall_dependencies(self, remove_weights: bool = True) -> bool:
        """
        Uninstall the model's dependencies by deleting its environment.

        Args:
            remove_weights: Also delete the downloaded model weights

        Returns:
            bool: True if uninstallation was successful, False otherwise
        """
        removed = self.env.remove()
        if remove_weights:
            removed = paths.remove_tree(self.weights_dir) and removed
        self.available = self.check_dependencies()
        return removed

    @abstractmethod
    def _install(self, log: LogCallback, cancel_event: Optional[threading.Event]) -> None:
        """Install the backend's packages into the freshly created environment."""

    def _verify(self, log: LogCallback, cancel_event: Optional[threading.Event]) -> dict:
        """Check that the installation works. Returns details for the install marker."""
        return {}

    @property
    def weights_dir(self) -> Path:
        """Directory where the backend stores downloaded model weights."""
        return paths.weights_dir(self.BACKEND)

    def installed_size(self) -> int:
        """Disk space used by the environment and its model weights."""
        return self.env.size() + paths.dir_size(self.weights_dir)

    # Model information ----------------------------------------------------

    @classmethod
    def get_available_models(cls) -> Dict[str, str]:
        """
        Get a dictionary of available models.

        Returns:
            Dict[str, str]: Model name -> description
        """
        return cls.AVAILABLE_MODELS

    @property
    def supports_two_stems(self) -> bool:
        """Whether the model can reduce its output to vocals/instrumental."""
        return False

    def get_stems(self, two_stems: bool = False) -> List[str]:
        """Names of the stems the model produces."""
        return list(self.SEPARATION_MODES.get(self.model_name, []))

    # Processing -----------------------------------------------------------

    def process(self, input_file: str, output_dir: str, two_stems: bool = False,
                progress_callback: ProgressCallback = None,
                cancel_event: Optional[threading.Event] = None,
                status_callback: StatusCallback = None,
                options: Optional[dict] = None) -> str:
        """
        Process an audio file and separate it into stems.

        Args:
            input_file: Path to audio file (any format FFmpeg can read)
            output_dir: Directory to save separated stems (as <stem>.wav)
            two_stems: Whether to separate into just vocals and instrumental
            progress_callback: Function to call with progress updates (0-100)
            cancel_event: Set to abort processing (raises ProcessCancelled)
            status_callback: Function to call with a short description of
                             the current step
            options: Processing options (see Settings.processing_options)

        Returns:
            Path to the directory with separated stems
        """
        if not self.available:
            raise ModelNotInstalledError(f"{self.name} is not installed. Install the model first.")

        options = options or {}
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        paths.weights_dir(self.BACKEND, create=True)

        def report(value: int) -> None:
            if progress_callback is not None:
                progress_callback(max(0, min(100, int(value))))

        last_status = [None]

        def status(text: str) -> None:
            # Backends repeat their status with every progress bar redraw
            if status_callback is not None and text != last_status[0]:
                last_status[0] = text
                status_callback(text)

        work_dir = Path(tempfile.mkdtemp(prefix="work_", dir=output_path))
        try:
            report(0)
            # Backends always get a plainly named file, whatever the source is called
            input_wav = work_dir / "input.wav"
            if ffmpeg.is_standard_wav(input_file):
                _link_or_copy(Path(input_file), input_wav)
            else:
                status("Converting audio...")
                ffmpeg.convert_to_wav(input_file, input_wav, cancel_event)
            report(3)

            status("Loading model...")
            raw_dir = work_dir / "raw"
            raw_dir.mkdir()
            stems = self._separate(
                input_wav, raw_dir, two_stems,
                lambda value: report(3 + value * 0.96),
                status, cancel_event, options,
            )
            if not stems:
                raise ModelError(f"{self.name} did not produce any stems.")

            for stem, source in stems.items():
                source = Path(source)
                if not source.is_file() or source.stat().st_size == 0:
                    raise ModelError(f"{self.name} did not produce the '{stem}' stem.")
                target = output_path / f"{stem}.wav"
                if target.exists():
                    target.unlink()
                shutil.move(str(source), str(target))
            report(100)
            return str(output_path)
        finally:
            paths.remove_tree(work_dir)

    @abstractmethod
    def _separate(self, input_wav: Path, raw_dir: Path, two_stems: bool,
                  progress: Callable[[float], None], status: Callable[[str], None],
                  cancel_event: Optional[threading.Event], options: dict) -> Dict[str, Path]:
        """
        Run the separation.

        Args:
            input_wav: 16-bit 44.1 kHz stereo WAV file to separate
            raw_dir: Empty directory the backend may write to
            two_stems: Whether to separate into just vocals and instrumental
            progress: Function to call with progress of this step (0-100)
            status: Function to call with a short description of the current step
            cancel_event: Set to abort processing
            options: Processing options

        Returns:
            Dict[str, Path]: Stem name -> path of the WAV file written
        """

    def _run_backend(self, args: List[str], on_line: Callable[[str], None],
                     cancel_event: Optional[threading.Event],
                     extra_env: Optional[dict] = None, command: Optional[List[str]] = None) -> None:
        """
        Run the backend's Python (or ``command``) and raise ModelError with
        the end of its output if it fails.
        """
        cmd = (command if command is not None else [str(self.env.python)]) + args
        returncode, tail = run_streaming(
            cmd,
            env=self.env.subprocess_env(extra_env),
            on_line=on_line,
            cancel_event=cancel_event,
        )
        if returncode != 0:
            # Progress bar redraws only bury the actual error message
            relevant = [line for line in tail if "%|" not in line and not line.startswith(PROGRESS_PREFIX)]
            details = "\n".join(relevant[-12:]) if relevant else "No output captured"
            raise ModelError(f"{self.name} failed (exit code {returncode}).\n\n{details}")

    @staticmethod
    def _runner_line_handler(progress: Callable[[float], None], status: Callable[[str], None],
                             log: LogCallback = None) -> Callable[[str], None]:
        """Line handler understanding the PROGRESS/STATUS protocol of the runner scripts."""
        def handle(line: str) -> None:
            if line.startswith(PROGRESS_PREFIX):
                try:
                    progress(float(line[len(PROGRESS_PREFIX):]))
                except ValueError:
                    pass
            elif line.startswith(STATUS_PREFIX):
                status(line[len(STATUS_PREFIX):].strip())
            elif log is not None:
                log(line)
        return handle


def _link_or_copy(source: Path, target: Path) -> None:
    """Make ``target`` refer to the contents of ``source`` as cheaply as possible."""
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


__all__ = [
    "BaseModel",
    "ModelError",
    "ModelNotInstalledError",
    "EnvError",
    "ProcessCancelled",
    "RUNNERS_DIR",
]
