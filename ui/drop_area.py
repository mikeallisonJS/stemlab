from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
import os
import mimetypes

class DropArea(QFrame):
    file_dropped = pyqtSignal(str)
    
    # Comprehensive list of audio file extensions
    AUDIO_EXTENSIONS = [
        # Common formats
        '.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', 
        # Additional formats
        '.mp2', '.mp4', '.wma', '.aiff', '.aif', '.aifc', '.ape',
        '.opus', '.wv', '.webm', '.au', '.snd', '.mid', '.midi',
        '.amr', '.awb', '.3gp', '.ac3', '.adts', '.caf', '.dts',
        '.gsm', '.m4b', '.m4p', '.mka', '.mpc', '.oga', '.mogg',
        '.ra', '.rm', '.tta', '.voc', '.vox', '.weba', '.8svx',
        '.spx'
    ]
    
    # Audio MIME types
    AUDIO_MIME_TYPES = [
        'audio/', 'application/ogg', 'application/octet-stream'
    ]
    
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 2px dashed #aaa;
                border-radius: 5px;
                padding: 20px;
            }
        """)
        
        # Layout
        layout = QVBoxLayout(self)
        
        # Label
        self.label = QLabel("Drag and drop an audio file here")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        
        self.setLayout(layout)
        
        # Ensure MIME types are initialized
        if not mimetypes.inited:
            mimetypes.init()
    
    def is_audio_file(self, file_path):
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
        if file_ext in self.AUDIO_EXTENSIONS:
            return True
            
        # Method 2: Check MIME type
        try:
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type and any(mime_type.startswith(audio_type) for audio_type in self.AUDIO_MIME_TYPES):
                return True
        except Exception:
            pass  # Fall back to extension-only check on error
            
        return False
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            # Check if it's an audio file
            url = event.mimeData().urls()[0]
            file_path = url.toLocalFile()
            
            if self.is_audio_file(file_path):
                event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if self.is_audio_file(file_path):
                self.file_dropped.emit(file_path)
            else:
                # If this is reached, it means dragEnterEvent accepted a non-audio file
                # This is a fallback for safety
                print(f"Rejected file: {file_path} - not recognized as audio")
    
    def set_file(self, file_name):
        self.label.setText(f"Selected file: {file_name}")
        self.setStyleSheet("""
            QFrame {
                background-color: #eaf7ea;
                border: 2px solid #6bc76b;
                border-radius: 5px;
                padding: 20px;
            }
        """) 