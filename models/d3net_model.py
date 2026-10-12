import sys
import threading
from pathlib import Path
from typing import Callable, Dict, Optional

from models.base_model import RUNNERS_DIR, BaseModel, LogCallback


class D3NetModel(BaseModel):
    """
    Wrapper for D3Net model from Sony AI Research.
    https://github.com/sony/ai-research-code/tree/master/d3net

    Uses Sony's official NNabla implementation and pretrained weights,
    converted to ONNX at install time so inference can run on the GPU
    (DirectML on Windows) or on all CPU cores.
    """

    BACKEND = "d3net"
    # NNabla publishes wheels up to Python 3.10
    PYTHON_VERSIONS = ((3, 10), (3, 9))
    INSTALL_SIZE = "about 700 MB"

    # Available D3Net models
    AVAILABLE_MODELS = {
        "standard": "Standard 4-source separation (vocals, drums, bass, other)",
        "fast": "Faster 4-source separation without channel-swap averaging",
    }

    # Default separation stems for different model types
    SEPARATION_MODES = {
        "standard": ["vocals", "drums", "bass", "other"],
        "fast": ["vocals", "drums", "bass", "other"],
    }

    # NNabla's own pins; the ONNX packages are the newest that work with them
    REQUIREMENTS = [
        "nnabla==1.39.0",
        "numpy~=1.26.0",
        "protobuf~=3.20",
        "onnx==1.16.2",
        "soundfile",
        "pyyaml",
    ]

    RUNNER = RUNNERS_DIR / "d3net_runner.py"

    def __init__(self, model_name="standard"):
        """
        Initialize D3Net model wrapper.

        Args:
            model_name: Name of the model to use (standard, fast)
        """
        self.separation_mode = model_name
        super().__init__(model_name)
        self.name = f"D3Net ({model_name})"

    def check_dependencies(self) -> bool:
        """Check if the D3Net environment and its converted networks are installed."""
        return self.env.is_installed() and all(
            (self.weights_dir / "onnx" / f"{stem}.onnx").is_file()
            for stem in self.SEPARATION_MODES["standard"]
        )

    def _install(self, log: LogCallback, cancel_event: Optional[threading.Event]) -> None:
        """Install NNabla and ONNX Runtime, then fetch and convert the pretrained networks."""
        # The DirectML build runs on any DirectX 12 GPU and includes the CPU provider
        runtime = "onnxruntime-directml==1.18.1" if sys.platform == "win32" else "onnxruntime==1.18.1"
        self.env.pip(["install"] + self.REQUIREMENTS + [runtime], log, cancel_event)
        # Only its ONNX exporter is used; its own dependencies would pull in TensorFlow
        self.env.pip(["install", "--no-deps", "nnabla-converter==1.39.0"], log, cancel_event)
        self.env.run_python(
            [str(self.RUNNER), "--data", str(self.weights_dir), "--setup"],
            log, cancel_event, action="download and convert the D3Net networks",
        )

    def _verify(self, log: LogCallback, cancel_event: Optional[threading.Event]) -> dict:
        self.env.run_python(
            ["-c", "import onnxruntime as ort, soundfile, yaml; "
                   "print('D3Net OK - ONNX Runtime', ort.__version__, ort.get_available_providers())"],
            log, cancel_event, action="verify the D3Net installation",
        )
        return {"package": "nnabla==1.39.0"}

    def _separate(self, input_wav: Path, raw_dir: Path, two_stems: bool,
                  progress: Callable[[float], None], status: Callable[[str], None],
                  cancel_event: Optional[threading.Event], options: dict) -> Dict[str, Path]:
        args = [
            str(self.RUNNER),
            "--data", str(self.weights_dir),
            "--input", str(input_wav),
            "--output", str(raw_dir),
            "--device", options.get("device", "auto"),
        ]
        if self.model_name == "standard":
            args.append("--flip-average")

        self._run_backend(args, self._runner_line_handler(progress, status), cancel_event)
        return {stem: raw_dir / f"{stem}.wav" for stem in self.get_stems()}
