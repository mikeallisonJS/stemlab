import sys
import threading
from pathlib import Path
from typing import Callable, Dict, Optional

from core.envs import IS_APPLE_SILICON
from models.base_model import RUNNERS_DIR, BaseModel, LogCallback


class SpleeterModel(BaseModel):
    """
    Wrapper for Spleeter model from Deezer Research.
    https://github.com/deezer/spleeter
    """

    BACKEND = "spleeter"
    # TensorFlow 2.12 has no builds for Python 3.12+
    PYTHON_VERSIONS = ((3, 10), (3, 11), (3, 9))
    INSTALL_SIZE = "about 1.5 GB"

    # Available Spleeter models
    AVAILABLE_MODELS = {
        "2stems": "Vocals and accompaniment separation",
        "4stems": "Vocals, drums, bass, and other separation",
        "5stems": "Vocals, drums, bass, piano, and other separation",
    }

    # Default separation stems for different model types
    SEPARATION_MODES = {
        "2stems": ["vocals", "accompaniment"],
        "4stems": ["vocals", "drums", "bass", "other"],
        "5stems": ["vocals", "drums", "bass", "piano", "other"],
    }

    SPLEETER_VERSION = "2.4.2"

    # Spleeter's own dependencies, minus TensorFlow which is platform specific
    REQUIREMENTS = [
        "httpx[http2]>=0.19.0,<0.20.0",
        "typer>=0.3.2,<0.4.0",
        "pandas>=1.3.0,<2.0.0",
        "norbert>=0.2.1,<0.3.0",
        "numpy<1.24",
        "ffmpeg-python>=0.2.0,<0.3.0",
        "soundfile",
    ]

    def __init__(self, model_name="2stems"):
        """
        Initialize Spleeter model wrapper.

        Args:
            model_name: Name of the Spleeter model to use (2stems, 4stems, 5stems)
        """
        # Detect if we're on Apple Silicon Mac
        self.is_apple_silicon = IS_APPLE_SILICON
        self.separation_mode = model_name
        super().__init__(model_name)
        self.name = f"Spleeter ({model_name})"

    def _tensorflow_requirements(self):
        """TensorFlow packages matching the platform."""
        if self.is_apple_silicon:
            # tensorflow-macos is the ARM build; the regular wheel needs AVX
            return ["tensorflow-macos==2.12.0"]
        if sys.platform == "win32":
            # Spleeter pins tensorflow-io-gcs-filesystem 0.32.0, which was never
            # published for Windows; 0.31.0 is the last release that was
            return ["tensorflow==2.12.1", "tensorflow-io-gcs-filesystem==0.31.0"]
        return ["tensorflow==2.12.1", "tensorflow-io-gcs-filesystem==0.32.0"]

    def _install(self, log: LogCallback, cancel_event: Optional[threading.Event]) -> None:
        """Install spleeter and its dependencies."""
        self.env.pip(["install"] + self._tensorflow_requirements() + self.REQUIREMENTS, log, cancel_event)
        if self.is_apple_silicon:
            # Metal GPU acceleration is optional
            try:
                self.env.pip(["install", "tensorflow-metal==0.8.0"], log, cancel_event)
            except Exception as e:
                if log is not None:
                    log(f"Warning: Could not install tensorflow-metal, continuing with CPU: {e}")
        # Dependencies are pinned above, so pip must not resolve Spleeter's own pins
        self.env.pip(["install", "--no-deps", f"spleeter=={self.SPLEETER_VERSION}"], log, cancel_event)

    def _verify(self, log: LogCallback, cancel_event: Optional[threading.Event]) -> dict:
        self.env.run_python(
            ["-c", "import tensorflow as tf, soundfile; from spleeter.separator import Separator; "
                   "print('Spleeter OK - TensorFlow', tf.__version__)"],
            log, cancel_event, extra_env={"TF_CPP_MIN_LOG_LEVEL": "2"},
            action="verify the Spleeter installation",
        )
        return {"package": f"spleeter=={self.SPLEETER_VERSION}"}

    def _separate(self, input_wav: Path, raw_dir: Path, two_stems: bool,
                  progress: Callable[[float], None], status: Callable[[str], None],
                  cancel_event: Optional[threading.Event], options: dict) -> Dict[str, Path]:
        args = [
            str(RUNNERS_DIR / "spleeter_runner.py"),
            "--input", str(input_wav),
            "--output", str(raw_dir),
            "--model", self.model_name,
            "--weights", str(self.weights_dir),
        ]
        if options.get("spleeter_mwf"):
            args.append("--mwf")

        self._run_backend(args, self._runner_line_handler(progress, status), cancel_event)
        return {stem: raw_dir / f"{stem}.wav" for stem in self.get_stems()}
