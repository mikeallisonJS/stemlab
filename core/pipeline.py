"""The separation workflow shared by the GUI and the command line."""

import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core import ffmpeg, paths

# Order in which stems are listed
STEM_ORDER = ["vocals", "drums", "bass", "guitar", "piano", "other",
              "no_vocals", "accompaniment", "instrumental"]


def sort_stems(stems: List[str]) -> List[str]:
    """Sort stem names into display order (unknown stems last, alphabetically)."""
    return sorted(stems, key=lambda stem: (STEM_ORDER.index(stem) if stem in STEM_ORDER else len(STEM_ORDER), stem))


class SeparationResult:
    """
    The outcome of separating one audio file.

    Attributes:
        source: The file the user selected
        title: Track name (source file name without extension)
        model_name: Name of the model variant, e.g. "htdemucs"
        model_label: Model name shown to the user
        directory: Working directory holding the files below
        mix: The source converted to WAV, for comparison with the stems
        stems: Stem name -> WAV file, in display order
    """

    def __init__(self, source: Path, model_name: str, model_label: str, directory: Path,
                 mix: Path, stems: Dict[str, Path]):
        self.source = Path(source)
        self.title = self.source.stem
        self.model_name = model_name
        self.model_label = model_label
        self.directory = Path(directory)
        self.mix = Path(mix)
        self.stems = {stem: Path(stems[stem]) for stem in sort_stems(list(stems))}

    def export_folder_name(self) -> str:
        """Folder name used when saving all stems, e.g. "My Song [htdemucs]"."""
        return paths.safe_name(f"{self.title} [{self.model_name}]")

    def discard(self) -> None:
        """Delete the working files of this result."""
        paths.remove_tree(self.directory)


def separate_file(model, source, session_dir, two_stems: bool = False,
                  options: Optional[dict] = None,
                  progress: Optional[Callable[[int], None]] = None,
                  status: Optional[Callable[[str], None]] = None,
                  cancel_event: Optional[threading.Event] = None,
                  model_label: Optional[str] = None) -> SeparationResult:
    """
    Separate an audio file into stems.

    Args:
        model: The separation model (a models.base_model.BaseModel)
        source: Path to the audio file
        session_dir: Directory below which a working directory is created
        two_stems: Whether to separate into just vocals and instrumental
        options: Processing options (see Settings.processing_options)
        progress: Function to call with progress updates (0-100)
        status: Function to call with a short description of the current step
        cancel_event: Set to abort (raises core.process.ProcessCancelled)
        model_label: Model name shown to the user (defaults to model.name)

    Returns:
        SeparationResult describing the files that were produced
    """
    source = Path(source)
    if not source.is_file():
        raise ffmpeg.AudioError(f"File not found: {source}")

    def report(value: float) -> None:
        if progress is not None:
            progress(max(0, min(100, int(value))))

    job_dir = Path(tempfile.mkdtemp(prefix="job_", dir=session_dir))
    try:
        report(0)
        if status is not None:
            status("Converting audio...")
        mix = ffmpeg.convert_to_wav(source, job_dir / "mix.wav", cancel_event)
        report(5)

        stems_dir = job_dir / "stems"
        model.process(
            str(mix), str(stems_dir),
            two_stems=two_stems,
            progress_callback=lambda value: report(5 + value * 0.95),
            cancel_event=cancel_event,
            status_callback=status,
            options=options,
        )
        stems = {path.stem: path for path in stems_dir.glob("*.wav")}
        report(100)
        return SeparationResult(source, model.model_name, model_label or model.name, job_dir, mix, stems)
    except BaseException:
        paths.remove_tree(job_dir)
        raise


class ExportFolders:
    """
    Hands out the folders stems are saved to while processing several files,
    keeping apart tracks that share a name (the same file name in two
    folders, or "song.mp3" next to "song.wav").
    """

    def __init__(self):
        self._owners: Dict[str, str] = {}

    def folder_for(self, result: SeparationResult, destination) -> Path:
        source = os.path.normcase(str(result.source))
        base = result.export_folder_name()
        number = 1
        while True:
            folder = Path(destination) / (base if number == 1 else f"{base} ({number})")
            owner = self._owners.setdefault(os.path.normcase(str(folder)), source)
            if owner == source:
                return folder
            number += 1


def export_result(result: SeparationResult, destination, fmt: str, bitrate: str,
                  progress: Optional[Callable[[int], None]] = None,
                  cancel_event: Optional[threading.Event] = None,
                  folders: Optional[ExportFolders] = None) -> Path:
    """
    Save all stems of a result into ``<destination>/<track> [<model>]/``.

    Args:
        folders: Shared between the files of one batch, so that tracks with
                 the same name do not overwrite each other's stems

    Returns:
        Path to the folder the stems were written to
    """
    if folders is not None:
        folder = folders.folder_for(result, destination)
    else:
        folder = Path(destination) / result.export_folder_name()
    folder.mkdir(parents=True, exist_ok=True)
    total = len(result.stems)
    for index, (stem, path) in enumerate(result.stems.items()):
        ffmpeg.export_audio(path, folder / stem, fmt, bitrate, cancel_event)
        if progress is not None:
            progress(int((index + 1) * 100 / total))
    return folder
