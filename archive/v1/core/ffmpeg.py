"""FFmpeg discovery plus audio conversion and export helpers."""

import functools
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

import soundfile as sf

from core import paths
from core.process import run_streaming, subprocess_flags

# Every separation model is fed audio in this format
SAMPLE_RATE = 44100
CHANNELS = 2


class AudioError(Exception):
    """Raised when an audio file cannot be read, converted or exported."""


class ExportFormat:
    """An audio format stems can be saved in."""

    def __init__(self, key: str, label: str, extension: str, codec_args: List[str], lossy: bool):
        self.key = key
        self.label = label
        self.extension = extension
        self.codec_args = codec_args
        self.lossy = lossy


EXPORT_FORMATS: Dict[str, ExportFormat] = {
    fmt.key: fmt
    for fmt in (
        ExportFormat("wav", "WAV (lossless)", ".wav", ["-c:a", "pcm_s16le"], False),
        ExportFormat("flac", "FLAC (lossless)", ".flac", ["-c:a", "flac"], False),
        ExportFormat("aiff", "AIFF (lossless)", ".aiff", ["-c:a", "pcm_s16be"], False),
        ExportFormat("mp3", "MP3", ".mp3", ["-c:a", "libmp3lame"], True),
        ExportFormat("m4a", "M4A (AAC)", ".m4a", ["-c:a", "aac"], True),
        ExportFormat("ogg", "OGG (Vorbis)", ".ogg", ["-c:a", "libvorbis"], True),
    )
}
# File name endings that are replaced by the extension of the export format
AUDIO_SUFFIXES = {fmt.extension for fmt in EXPORT_FORMATS.values()} | {".aif", ".m4b", ".oga", ".wave"}
DEFAULT_EXPORT_FORMAT = "wav"
BITRATES = ["128k", "192k", "256k", "320k"]
DEFAULT_BITRATE = "320k"


@functools.lru_cache(maxsize=1)
def find_ffmpeg() -> Optional[str]:
    """
    Locate an FFmpeg executable: the system one if installed, otherwise the
    binary bundled with the imageio-ffmpeg package.
    """
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def has_system_ffmpeg() -> bool:
    """Whether FFmpeg is installed system-wide (on the PATH)."""
    return shutil.which("ffmpeg") is not None


def require_ffmpeg() -> str:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise AudioError(
            "FFmpeg was not found. Reinstall the application requirements "
            "(pip install -r requirements.txt) or install FFmpeg and add it to your PATH."
        )
    return ffmpeg


@functools.lru_cache(maxsize=1)
def ffmpeg_path_dir() -> Optional[str]:
    """
    Directory to prepend to PATH so that model backends find an ``ffmpeg``
    command. Returns None when FFmpeg is already on the PATH.
    """
    if has_system_ffmpeg():
        return None
    bundled = find_ffmpeg()
    if not bundled:
        return None
    target = paths.bin_dir() / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    try:
        if not target.exists() or target.stat().st_size != os.path.getsize(bundled):
            shutil.copy2(bundled, target)
    except OSError:
        return None
    return str(target.parent)


def is_standard_wav(path) -> bool:
    """Whether a file already is 16-bit 44.1 kHz stereo WAV."""
    try:
        info = sf.info(str(path))
    except Exception:
        return False
    return (
        info.format == "WAV"
        and info.samplerate == SAMPLE_RATE
        and info.channels == CHANNELS
        and info.subtype == "PCM_16"
    )


_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def media_duration(path) -> Optional[float]:
    """Duration of an audio file in seconds, or None if it cannot be read."""
    try:
        info = sf.info(str(path))
        if info.samplerate:
            return info.frames / float(info.samplerate)
    except Exception:
        pass
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostdin", "-i", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            **subprocess_flags(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if "Audio:" not in result.stdout:
        return None
    match = _DURATION.search(result.stdout)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _run_ffmpeg(args: List[str], cancel_event: Optional[threading.Event], action: str) -> None:
    cmd = [require_ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y"] + args
    returncode, tail = run_streaming(cmd, cancel_event=cancel_event)
    if returncode != 0:
        details = "\n".join(tail[-5:]) if tail else "no output"
        raise AudioError(f"FFmpeg could not {action}:\n{details}")


def convert_to_wav(src, dst, cancel_event: Optional[threading.Event] = None) -> Path:
    """
    Decode any audio file FFmpeg understands into 16-bit 44.1 kHz stereo WAV.

    Args:
        src: Path to the input audio file
        dst: Path of the WAV file to create
        cancel_event: Set to abort the conversion

    Returns:
        Path to the converted file
    """
    src, dst = Path(src), Path(dst)
    if not src.is_file():
        raise AudioError(f"File not found: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        ["-i", str(src), "-vn", "-map", "0:a:0", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE),
         "-c:a", "pcm_s16le", str(dst)],
        cancel_event,
        f"read '{src.name}' as audio",
    )
    if not dst.is_file() or dst.stat().st_size <= 44:
        raise AudioError(f"'{src.name}' does not contain any audio.")
    return dst


def export_audio(src, dst, fmt: str = DEFAULT_EXPORT_FORMAT, bitrate: str = DEFAULT_BITRATE,
                 cancel_event: Optional[threading.Event] = None) -> Path:
    """
    Save a WAV stem in the requested format.

    Args:
        src: Path to the WAV file to export
        dst: Destination path. The extension of the format is appended, or
             replaces an audio extension the name already ends with
        fmt: Key of an entry in EXPORT_FORMATS
        bitrate: Bitrate for lossy formats, e.g. "320k"

    Returns:
        Path to the written file
    """
    if fmt not in EXPORT_FORMATS:
        raise AudioError(f"Unsupported export format: {fmt}")
    export_format = EXPORT_FORMATS[fmt]
    src = Path(src)
    dst = Path(dst)
    if dst.suffix.lower() in AUDIO_SUFFIXES:
        dst = dst.with_suffix(export_format.extension)
    else:
        # "Mr. Brightside - vocals" has no extension: ".Brightside - vocals" is part of the name
        dst = dst.with_name(dst.name + export_format.extension)
    dst.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "wav":
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return dst

    args = ["-i", str(src)] + export_format.codec_args
    if export_format.lossy:
        args += ["-b:a", bitrate if bitrate in BITRATES else DEFAULT_BITRATE]
    _run_ffmpeg(args + [str(dst)], cancel_event, f"export '{dst.name}'")
    return dst


def install_hint() -> str:
    """Platform specific instructions for installing FFmpeg system-wide."""
    if sys.platform == "win32":
        return "winget install Gyan.FFmpeg   (or: choco install ffmpeg)"
    if sys.platform == "darwin":
        return "brew install ffmpeg"
    return "sudo apt install ffmpeg   (or use your distribution's package manager)"
