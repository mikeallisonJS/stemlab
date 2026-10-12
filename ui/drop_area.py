from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
import os
import mimetypes

class DropArea(QFrame):
    files_dropped = pyqtSignal(list)
    browse_requested = pyqtSignal()

    # Comprehensive list of audio file extensions
    AUDIO_EXTENSIONS = [
        # Common formats
        '.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac',
        # Additional formats
        '.mp2', '.wma', '.aiff', '.aif', '.aifc', '.ape',
        '.opus', '.wv', '.au', '.snd',
        '.amr', '.awb', '.3gp', '.ac3', '.adts', '.caf', '.dts',
        '.gsm', '.m4b', '.m4p', '.mka', '.mpc', '.oga', '.mogg',
        '.ra', '.rm', '.tta', '.voc', '.vox', '.weba', '.8svx',
        '.spx',
        # Video containers (the audio track is used)
        '.mp4', '.m4v', '.mov', '.mkv', '.webm', '.avi'
    ]

    # Reported as audio by their MIME type, but hold notes instead of sound
    NOT_AUDIO_EXTENSIONS = ['.mid', '.midi', '.kar', '.m3u', '.m3u8', '.pls']

    # Audio MIME types
    AUDIO_MIME_TYPES = [
        'audio/', 'application/ogg'
    ]

    IDLE_STYLE = """
        DropArea {
            background-color: palette(base);
            border: 2px dashed palette(mid);
            border-radius: 5px;
        }
    """

    ACTIVE_STYLE = """
        DropArea {
            background-color: palette(alternate-base);
            border: 2px dashed palette(highlight);
            border-radius: 5px;
        }
    """

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(90)
        self.setStyleSheet(self.IDLE_STYLE)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        # Label
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        self.set_message("Drag audio files here")

        # Ensure MIME types are initialized
        if not mimetypes.inited:
            mimetypes.init()

    @classmethod
    def file_dialog_filter(cls):
        """Name filter for file dialogs listing the supported extensions."""
        patterns = " ".join(f"*{ext}" for ext in cls.AUDIO_EXTENSIONS)
        return f"Audio Files ({patterns});;All Files (*)"

    @classmethod
    def is_audio_file(cls, file_path):
        """
        Check if the given file is an audio file using multiple methods:
        1. Check file extension against known audio extensions
        2. Check MIME type if extension check fails

        Args:
            file_path: Path to the file to check

        Returns:
            bool: True if file is likely an audio file, False otherwise
        """
        # Method 1: Check extension
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext in cls.AUDIO_EXTENSIONS:
            return True
        if file_ext in cls.NOT_AUDIO_EXTENSIONS:
            return False

        # Method 2: Check MIME type
        try:
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type and any(mime_type.startswith(audio_type) for audio_type in cls.AUDIO_MIME_TYPES):
                return True
        except Exception:
            pass  # Fall back to extension-only check on error

        return False

    @classmethod
    def collect_audio_files(cls, paths):
        """
        Expand a list of dropped files and folders into audio files.
        Folders are searched recursively.

        Args:
            paths: Paths of files and directories

        Returns:
            list: Audio file paths, without duplicates, in a stable order
        """
        found = []
        for path in paths:
            if os.path.isdir(path):
                for root, _dirs, files in os.walk(path):
                    for name in sorted(files):
                        candidate = os.path.join(root, name)
                        if cls.is_audio_file(candidate):
                            found.append(candidate)
            elif os.path.isfile(path) and cls.is_audio_file(path):
                found.append(path)
        return list(dict.fromkeys(os.path.normpath(path) for path in found))

    def _local_paths(self, event):
        return [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]

    def dragEnterEvent(self, event: QDragEnterEvent):
        if not event.mimeData().hasUrls():
            return
        # Accept if anything dropped could be audio; folders are checked on drop
        paths = self._local_paths(event)
        if any(os.path.isdir(path) or self.is_audio_file(path) for path in paths):
            self.setStyleSheet(self.ACTIVE_STYLE)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.IDLE_STYLE)

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(self.IDLE_STYLE)
        files = self.collect_audio_files(self._local_paths(event))
        if files:
            event.acceptProposedAction()
            self.files_dropped.emit(files)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.browse_requested.emit()

    def set_message(self, message, hint="or click to browse"):
        """Set a custom message in the drop area."""
        text = f"<span style='font-size: 14pt;'>{message}</span>"
        if hint:
            text += f"<br><span style='font-size: 9pt;'>{hint}</span>"
        self.label.setText(text)
