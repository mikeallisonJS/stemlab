import os
import tempfile
import shutil
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget,
    QLabel, QPushButton, QFileDialog, QGridLayout,
    QFrame, QProgressBar, QSizePolicy, QSlider
)
from PyQt6.QtCore import Qt, QUrl, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

import numpy as np
import soundfile as sf
import librosa
import librosa.display
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas


class WaveformWidget(QFrame):
    """Custom widget to display and play audio waveforms."""
    
    playback_position_changed = pyqtSignal(int)
    
    def __init__(self, audio_file, stem_name, parent=None):
        super().__init__(parent)
        self.audio_file = audio_file
        self.stem_name = stem_name
        self.waveform_data = None
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)
        self.is_playing = False
        self.duration = 0
        self.current_position = 0
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(200)
        
        self.init_ui()
        self.load_audio()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Title
        title_layout = QHBoxLayout()
        title = QLabel(f"<b>{self.stem_name.capitalize()}</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title_layout.addWidget(title)
        
        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.setMaximumWidth(80)
        self.save_button.clicked.connect(self.save_audio)
        title_layout.addWidget(self.save_button)
        
        layout.addLayout(title_layout)
        
        # Waveform visualization
        self.figure = plt.figure(figsize=(7, 2))
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(80)
        layout.addWidget(self.canvas)
        
        # Playback controls
        controls_layout = QHBoxLayout()
        
        self.play_button = QPushButton("▶️ Play")
        self.play_button.clicked.connect(self.toggle_playback)
        self.play_button.setMaximumWidth(100)
        controls_layout.addWidget(self.play_button)
        
        self.playback_slider = QSlider(Qt.Orientation.Horizontal)
        self.playback_slider.setMinimum(0)
        self.playback_slider.setMaximum(1000)  # Will be updated when audio is loaded
        self.playback_slider.sliderMoved.connect(self.seek)
        controls_layout.addWidget(self.playback_slider)
        
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setMinimumWidth(100)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        controls_layout.addWidget(self.time_label)
        
        layout.addLayout(controls_layout)
    
    def load_audio(self):
        """Load audio and display waveform."""
        try:
            # Load audio file
            y, sr = librosa.load(self.audio_file, sr=None)
            self.waveform_data = y
            
            # Set player source
            self.player.setSource(QUrl.fromLocalFile(self.audio_file))
            
            # Plot waveform
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.plot(np.linspace(0, len(y)/sr, len(y)), y, linewidth=0.5, color='#2a82da')
            ax.set_axis_off()
            ax.set_ylim(-1, 1)
            self.figure.tight_layout(pad=0)
            self.canvas.draw()
            
            # Display audio information
            duration_sec = librosa.get_duration(y=y, sr=sr)
            minutes = int(duration_sec // 60)
            seconds = int(duration_sec % 60)
            self.time_label.setText(f"0:00 / {minutes}:{seconds:02d}")
            
        except Exception as e:
            print(f"Error loading audio file {self.audio_file}: {e}")
    
    def toggle_playback(self):
        """Toggle play/pause playback."""
        if self.is_playing:
            self.player.pause()
            self.play_button.setText("▶️ Play")
        else:
            self.player.play()
            self.play_button.setText("⏸️ Pause")
        
        self.is_playing = not self.is_playing
    
    def update_position(self, position):
        """Update slider position and time display during playback."""
        self.current_position = position
        
        # Update slider
        if self.duration > 0:
            self.playback_slider.setValue(int(position * 1000 / self.duration))
            
        # Update time display
        position_sec = position / 1000
        minutes = int(position_sec // 60)
        seconds = int(position_sec % 60)
        
        duration_sec = self.duration / 1000
        dur_minutes = int(duration_sec // 60)
        dur_seconds = int(duration_sec % 60)
        
        self.time_label.setText(f"{minutes}:{seconds:02d} / {dur_minutes}:{dur_seconds:02d}")
        
        # Reset button state when playback finishes
        if position >= self.duration and self.duration > 0:
            self.is_playing = False
            self.play_button.setText("▶️ Play")
            self.player.setPosition(0)
    
    def update_duration(self, duration):
        """Update total duration when media loads."""
        self.duration = duration
    
    def seek(self, position):
        """Seek to a position in the audio file."""
        if self.duration > 0:
            new_pos = int(position * self.duration / 1000)
            self.player.setPosition(new_pos)
    
    def save_audio(self):
        """Save the audio file to a user-selected location."""
        default_filename = os.path.basename(self.audio_file)
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Audio File", default_filename, "Audio Files (*.wav);;All Files (*.*)"
        )
        
        if file_path:
            try:
                # Copy the audio file to the selected location
                shutil.copy2(self.audio_file, file_path)
                print(f"File saved to: {file_path}")
            except Exception as e:
                print(f"Error saving file: {e}")
    
    def stop_playback(self):
        """Stop audio playback."""
        if self.is_playing:
            self.player.stop()
            self.is_playing = False
            self.play_button.setText("▶️ Play")


class ResultsWindow(QDialog):
    """Window to display processed audio stems with waveform visualization and playback."""
    
    def __init__(self, parent=None, source_dir=None, source_audio=None, model_name=None):
        super().__init__(parent)
        self.source_dir = source_dir
        self.source_audio = source_audio  # Original audio file
        self.model_name = model_name
        self.temp_dir = None
        self.waveform_widgets = []
        
        # Create a temporary directory to store all results
        self.temp_dir = tempfile.mkdtemp(prefix="captainstems_results_")
        
        # Copy all files from source_dir to temp_dir
        if source_dir and os.path.exists(source_dir):
            for file_name in os.listdir(source_dir):
                if file_name.endswith(".wav") or file_name.endswith(".mp3"):
                    src = os.path.join(source_dir, file_name)
                    dst = os.path.join(self.temp_dir, file_name)
                    shutil.copy2(src, dst)
        
        self.setWindowTitle(f"Audio Separation Results - {model_name}")
        self.setMinimumSize(700, 500)
        self.init_ui()
        
    def init_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        
        # Title
        title = QLabel(f"<h2>Audio Separation Results</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)
        
        # Model info
        if self.model_name:
            model_info = QLabel(f"<h3>Model: {self.model_name}</h3>")
            model_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            main_layout.addWidget(model_info)
        
        # Scroll area for waveforms
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # Load audio files from the temporary directory
        audio_files = []
        if self.temp_dir and os.path.exists(self.temp_dir):
            for file_name in os.listdir(self.temp_dir):
                if file_name.endswith((".wav", ".mp3")):
                    file_path = os.path.join(self.temp_dir, file_name)
                    # Get stem name from filename (remove extension)
                    stem_name = os.path.splitext(file_name)[0]
                    audio_files.append((file_path, stem_name))
        
        # Sort files by stem names (vocals first, then drums, bass, other)
        stem_order = {"vocals": 0, "drums": 1, "bass": 2, "other": 3, "piano": 4, "guitar": 5}
        audio_files.sort(key=lambda x: stem_order.get(x[1], 99))
        
        # Add waveform widgets for each audio file
        for file_path, stem_name in audio_files:
            waveform_widget = WaveformWidget(file_path, stem_name)
            scroll_layout.addWidget(waveform_widget)
            self.waveform_widgets.append(waveform_widget)
        
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        self.save_all_button = QPushButton("Save All Files")
        self.save_all_button.clicked.connect(self.save_all_files)
        button_layout.addWidget(self.save_all_button)
        
        button_layout.addStretch()
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close_window)
        button_layout.addWidget(self.close_button)
        
        main_layout.addLayout(button_layout)
    
    def save_all_files(self):
        """Save all audio files to a user-selected directory."""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Directory to Save All Files"
        )
        
        if dir_path:
            try:
                for file_name in os.listdir(self.temp_dir):
                    if file_name.endswith((".wav", ".mp3")):
                        src = os.path.join(self.temp_dir, file_name)
                        dst = os.path.join(dir_path, file_name)
                        shutil.copy2(src, dst)
                
                print(f"All files saved to: {dir_path}")
            except Exception as e:
                print(f"Error saving files: {e}")
    
    def close_window(self):
        """Close the dialog and clean up."""
        # Stop any ongoing playback
        for widget in self.waveform_widgets:
            widget.stop_playback()
        
        self.accept()
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Stop any ongoing playback
        for widget in self.waveform_widgets:
            widget.stop_playback()
        
        # Don't delete temp files when debugging
        # if self.temp_dir and os.path.exists(self.temp_dir):
        #    shutil.rmtree(self.temp_dir)
        
        event.accept() 