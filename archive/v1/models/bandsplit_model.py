import re
import threading
from pathlib import Path
from typing import Callable, Dict, Optional

from core.envs import torch_install_args
from core.process import BarProgress
from models.base_model import BaseModel, LogCallback, ModelError


class BandSplitModel(BaseModel):
    """
    Wrapper for Band-Split RoFormer models, run through python-audio-separator.
    https://github.com/nomadkaraoke/python-audio-separator

    Band-Split RoFormer is the successor of Band-Split RNN: it keeps the
    band-split front end and replaces the RNNs with transformers. Unlike
    Band-Split RNN it has publicly released pretrained weights.
    """

    BACKEND = "bandsplit"
    PYTHON_VERSIONS = ((3, 10), (3, 11), (3, 12))
    INSTALL_SIZE = "about 6 GB with GPU support, 2 GB without (plus 650 MB per model)"

    # Available Band-Split RoFormer models
    AVAILABLE_MODELS = {
        "vocals": "Vocals and instrumental separation (highest vocal quality)",
        "6stems": "Vocals, drums, bass, guitar, piano, and other separation",
    }

    # Default separation stems for different model types
    SEPARATION_MODES = {
        "vocals": ["vocals", "instrumental"],
        "6stems": ["vocals", "drums", "bass", "guitar", "piano", "other"],
    }

    # Checkpoint used for each model
    CHECKPOINTS = {
        "vocals": "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
        "6stems": "BS-Roformer-SW.ckpt",
    }

    AUDIO_SEPARATOR_VERSION = "0.47.0"

    # audio-separator names its output "<input>_(<Stem>)_<model>.wav"
    _STEM_IN_FILENAME = re.compile(r"_\(([^()]+)\)_")

    def __init__(self, model_name="vocals"):
        """
        Initialize Band-Split RoFormer model wrapper.

        Args:
            model_name: Name of the model to use (vocals, 6stems)
        """
        self.separation_mode = model_name
        super().__init__(model_name)
        self.name = f"Band-Split RoFormer ({model_name})"

    def _install(self, log: LogCallback, cancel_event: Optional[threading.Event]) -> None:
        """Install audio-separator and its dependencies."""
        # PyTorch first, so the build matching this machine's GPU is used
        torch_args = torch_install_args()
        extra = "cpu"
        if torch_args:
            self.env.pip(["install"] + torch_args, log, cancel_event)
            if "cu" in torch_args[-1].rsplit("/", 1)[-1]:
                extra = "gpu"
        self.env.pip(
            ["install", f"audio-separator[{extra}]=={self.AUDIO_SEPARATOR_VERSION}"],
            log, cancel_event,
        )

    def _verify(self, log: LogCallback, cancel_event: Optional[threading.Event]) -> dict:
        self.env.run_python(
            ["-c", "import torch; from audio_separator.separator import Separator; "
                   "print('audio-separator OK - PyTorch', torch.__version__, "
                   "'- GPU available' if torch.cuda.is_available() else '- CPU only')"],
            log, cancel_event, action="verify the Band-Split RoFormer installation",
        )
        return {"package": f"audio-separator=={self.AUDIO_SEPARATOR_VERSION}"}

    def _separate(self, input_wav: Path, raw_dir: Path, two_stems: bool,
                  progress: Callable[[float], None], status: Callable[[str], None],
                  cancel_event: Optional[threading.Event], options: dict) -> Dict[str, Path]:
        args = [
            str(input_wav),
            "--model_filename", self.CHECKPOINTS[self.model_name],
            "--model_file_dir", str(self.weights_dir),
            "--output_dir", str(raw_dir),
            "--output_format", "WAV",
            # Keep the level of the stems identical to the mix
            "--normalization", "1.0",
        ]

        extra_env = {}
        if options.get("device") == "cpu":
            # audio-separator has no device option; hiding the GPU forces CPU
            extra_env["CUDA_VISIBLE_DEVICES"] = ""

        bars = BarProgress(1, progress, accept=lambda line: "it/s" in line or "s/it" in line)

        def on_line(line: str) -> None:
            if bars.feed(line):
                if "it/s" in line or "s/it" in line:
                    status("Separating stems...")
                else:
                    status("Downloading model weights...")
            elif "Downloading" in line:
                status("Downloading model weights...")

        self._run_backend(args, on_line, cancel_event, extra_env=extra_env,
                          command=[str(self.env.script("audio-separator"))])

        found = {}
        for path in raw_dir.glob("*.wav"):
            match = self._STEM_IN_FILENAME.search(path.name)
            if match:
                found[match.group(1).strip().lower()] = path
        missing = [stem for stem in self.get_stems() if stem not in found]
        if missing:
            raise ModelError(f"{self.name} did not produce these stems: {', '.join(missing)}")
        return {stem: found[stem] for stem in self.get_stems()}
