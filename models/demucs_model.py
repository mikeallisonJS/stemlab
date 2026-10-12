import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.envs import torch_install_args
from core.process import BarProgress
from models.base_model import BaseModel, LogCallback


class DemucsModel(BaseModel):
    """
    Wrapper for Demucs models from Facebook Research.
    https://github.com/adefossez/demucs
    """

    BACKEND = "demucs"
    PYTHON_VERSIONS = ((3, 10), (3, 11), (3, 12))
    INSTALL_SIZE = "about 5 GB with GPU support, 1.5 GB without"

    # Demucs v4 models (Hybrid Transformer Demucs)
    V4_MODELS = {
        "htdemucs": "Hybrid Transformer Demucs v4 (default)",
        "htdemucs_ft": "Hybrid Transformer Demucs v4 fine-tuned (best quality, 4x slower)",
        "htdemucs_6s": "Hybrid Transformer Demucs v4 for 6 sources separation",
    }

    # Demucs v3 models (Hybrid Demucs)
    V3_MODELS = {
        "hdemucs_mmi": "Hybrid Demucs v3 trained on MusDB plus 800 extra songs",
        "mdx": "Hybrid Demucs v3, winner of the MDX challenge track A (MusDB only)",
        "mdx_extra": "Hybrid Demucs v3 with extra training data (MDX challenge track B)",
    }

    # Available Demucs models
    AVAILABLE_MODELS = {**V4_MODELS, **V3_MODELS}

    # Default separation stems for different model types
    SEPARATION_MODES = {
        "v3": ["drums", "bass", "other", "vocals"],
        "v4_standard": ["drums", "bass", "other", "vocals"],
        "v4_6stem": ["drums", "bass", "other", "vocals", "guitar", "piano"],
    }

    # Models that are a bag of several networks, each printing its own progress bar
    BAG_SIZES = {"htdemucs_ft": 4, "mdx": 4, "mdx_extra": 4}

    def __init__(self, model_name="htdemucs"):
        """
        Initialize Demucs model wrapper.

        Args:
            model_name: Name of the Demucs model to use
        """
        # Determine if this is a v3 or v4 model
        self.is_v3 = model_name in self.V3_MODELS
        self.is_6stem = model_name == "htdemucs_6s"

        # Set separation mode based on model type
        if self.is_v3:
            self.separation_mode = "v3"
        elif self.is_6stem:
            self.separation_mode = "v4_6stem"
        else:
            self.separation_mode = "v4_standard"

        super().__init__(model_name)
        self.name = f"Demucs ({model_name})"

    def _install(self, log: LogCallback, cancel_event: Optional[threading.Event]) -> None:
        """Install demucs and its dependencies."""
        # PyTorch first, so the build matching this machine's GPU is used
        torch_args = torch_install_args()
        if torch_args:
            self.env.pip(["install"] + torch_args, log, cancel_event)
        self.env.pip(["install", "demucs==4.1.0", "soundfile"], log, cancel_event)

    def _verify(self, log: LogCallback, cancel_event: Optional[threading.Event]) -> dict:
        self.env.run_python(
            ["-c", "import demucs.separate, torch; "
                   "print('Demucs', demucs.__version__, '- PyTorch', torch.__version__, "
                   "'- GPU available' if torch.cuda.is_available() else '- CPU only')"],
            log, cancel_event, action="verify the Demucs installation",
        )
        return {"package": "demucs==4.1.0"}

    @property
    def supports_two_stems(self) -> bool:
        return True

    def get_stems(self, two_stems: bool = False) -> List[str]:
        if two_stems:
            return ["vocals", "no_vocals"]
        return list(self.SEPARATION_MODES[self.separation_mode])

    def get_model_cmd_args(self, two_stems=False, options: Optional[dict] = None):
        """
        Get the command-line arguments for the selected model.

        Args:
            two_stems: Whether to separate into just vocals and instrumental
            options: Processing options (device, demucs_shifts, demucs_overlap)

        Returns:
            list: Command-line arguments for Demucs
        """
        options = options or {}
        cmd_args = ["-n", self.model_name]

        # Add two-stems option if requested
        if two_stems:
            cmd_args.append("--two-stems=vocals")

        # Demucs picks CUDA when available; only pass an explicit choice
        device = options.get("device", "auto")
        if device != "auto":
            cmd_args.extend(["-d", device])

        shifts = int(options.get("demucs_shifts", 1))
        if shifts > 1:
            cmd_args.extend(["--shifts", str(shifts)])

        overlap = options.get("demucs_overlap")
        if overlap is not None:
            cmd_args.extend(["--overlap", f"{float(overlap):.2f}"])

        return cmd_args

    def _separate(self, input_wav: Path, raw_dir: Path, two_stems: bool,
                  progress: Callable[[float], None], status: Callable[[str], None],
                  cancel_event: Optional[threading.Event], options: dict) -> Dict[str, Path]:
        # We're using subprocess to call the demucs command line tool
        # This gives us better compatibility than using the Python API directly
        args = (
            ["-m", "demucs.separate"]
            + self.get_model_cmd_args(two_stems, options)
            + ["-o", str(raw_dir), "--filename", "{stem}.{ext}", str(input_wav)]
        )

        shifts = max(1, int(options.get("demucs_shifts", 1)))
        bars = BarProgress(
            self.BAG_SIZES.get(self.model_name, 1) * shifts,
            progress,
            # Separation bars count seconds of audio; weight downloads count bytes
            accept=lambda line: "seconds/s" in line,
        )

        def on_line(line: str) -> None:
            if bars.feed(line):
                if "seconds/s" in line:
                    status("Separating stems...")
                else:
                    status("Downloading model weights...")
            elif "Downloading" in line:
                status("Downloading model weights...")

        self._run_backend(args, on_line, cancel_event, extra_env={
            # Keep downloaded weights with the application so they can be removed again
            "TORCH_HOME": str(self.weights_dir / "torch"),
            "HF_HOME": str(self.weights_dir / "huggingface"),
        })

        # Demucs creates a subdirectory named after the model
        model_dir = raw_dir / self.model_name
        return {stem: model_dir / f"{stem}.wav" for stem in self.get_stems(two_stems)}
