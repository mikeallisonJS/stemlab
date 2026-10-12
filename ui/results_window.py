import html
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget,
    QLabel, QPushButton, QFileDialog, QFrame, QSlider, QComboBox,
    QMessageBox
)
from PyQt6.QtCore import Qt, QThreadPool, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from core import ffmpeg, paths, pipeline
from core.audio import format_time
from ui.waveform import WaveformView
from ui.workers import FunctionWorker

STEM_TITLES = {
    "no_vocals": "Instrumental (no vocals)",
    "accompaniment": "Accompaniment",
}


def stem_title(stem):
    """Name of a stem as shown to the user."""
    return STEM_TITLES.get(stem, stem.replace("_", " ").capitalize())


class StemRow(QFrame):
    """One audio track of the results: title, waveform, play and save buttons."""

    play_clicked = pyqtSignal(object)
    seek_requested = pyqtSignal(object, float)
    save_clicked = pyqtSignal(object)

    def __init__(self, audio_file, title, stem=None, parent=None):
        super().__init__(parent)
        self.audio_file = str(audio_file)
        self.title = title
        # Name of the stem, or None for the original mix
        self.stem = stem

        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        # Title and buttons
        header_layout = QHBoxLayout()
        title_label = QLabel(f"<b>{html.escape(title)}</b>")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.play_button = QPushButton("▶ Play")
        self.play_button.setMinimumWidth(90)
        self.play_button.clicked.connect(lambda: self.play_clicked.emit(self))
        header_layout.addWidget(self.play_button)

        if stem is not None:
            self.save_button = QPushButton("Save...")
            self.save_button.clicked.connect(lambda: self.save_clicked.emit(self))
            header_layout.addWidget(self.save_button)

        layout.addLayout(header_layout)

        # Waveform visualization
        self.waveform = WaveformView(self.audio_file)
        self.waveform.seek_requested.connect(lambda fraction: self.seek_requested.emit(self, fraction))
        layout.addWidget(self.waveform)

    def set_state(self, active, playing):
        """Update the row for the current playback state."""
        self.waveform.set_active(active)
        self.play_button.setText("‖ Pause" if (active and playing) else "▶ Play")


class ResultsWindow(QDialog):
    """Window to display processed audio stems with waveform visualization and playback."""

    def __init__(self, parent, result, settings):
        """
        Args:
            parent: Parent widget
            result: The pipeline.SeparationResult to show
            settings: The application Settings
        """
        super().__init__(parent)
        self.result = result
        self.settings = settings
        self.rows = []
        self.current_row = None
        self.pending_position = None
        self.pending_play = False
        self.switching_source = False
        self.export_worker = None
        self.saved_folder = None

        # All tracks have the length of the mix
        duration = ffmpeg.media_duration(result.mix) or 0
        self.duration_ms = int(duration * 1000)

        # One player shared by all rows, so switching stems keeps the position
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.on_position_changed)
        self.player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.player.errorOccurred.connect(self.on_player_error)

        self.setWindowTitle(f"{result.title} - {result.model_label}")
        self.setMinimumSize(760, 560)
        self.init_ui()

    def init_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)

        # Title
        # File names may contain characters that mean something in HTML
        title = QLabel(f"<h2>{html.escape(self.result.title)}</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setTextFormat(Qt.TextFormat.RichText)
        main_layout.addWidget(title)

        # Model info
        model_info = QLabel(f"Model: {self.result.model_label}  ·  {len(self.result.stems)} stems")
        model_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(model_info)

        hint = QLabel("Click a waveform to jump there. Switching between tracks keeps the position.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setEnabled(False)
        main_layout.addWidget(hint)

        # Scroll area for waveforms
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # The original mix first, for comparison, then one row per stem
        self.add_row(scroll_layout, StemRow(self.result.mix, "Original mix"))
        for stem, path in self.result.stems.items():
            self.add_row(scroll_layout, StemRow(path, stem_title(stem), stem))

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)

        # Playback position and volume
        playback_layout = QHBoxLayout()
        self.time_label = QLabel()
        self.time_label.setMinimumWidth(110)
        playback_layout.addWidget(self.time_label)
        playback_layout.addStretch()
        playback_layout.addWidget(QLabel("Volume:"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(140)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        playback_layout.addWidget(self.volume_slider)
        main_layout.addLayout(playback_layout)
        self.on_volume_changed(self.volume_slider.value())
        self.update_time_label(0)

        # Export controls
        button_layout = QHBoxLayout()

        button_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        for key, export_format in ffmpeg.EXPORT_FORMATS.items():
            self.format_combo.addItem(export_format.label, key)
        self.format_combo.setCurrentIndex(self.format_combo.findData(self.settings.export_format()))
        self.format_combo.currentIndexChanged.connect(self.on_format_changed)
        button_layout.addWidget(self.format_combo)

        self.bitrate_combo = QComboBox()
        for bitrate in ffmpeg.BITRATES:
            self.bitrate_combo.addItem(bitrate.replace("k", " kbps"), bitrate)
        self.bitrate_combo.setCurrentIndex(self.bitrate_combo.findData(self.settings.export_bitrate()))
        self.bitrate_combo.currentIndexChanged.connect(self.on_format_changed)
        button_layout.addWidget(self.bitrate_combo)

        self.save_all_button = QPushButton("Save All Files...")
        self.save_all_button.clicked.connect(self.save_all_files)
        button_layout.addWidget(self.save_all_button)

        self.status_label = QLabel()
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        button_layout.addWidget(self.status_label, 1)

        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.setVisible(False)
        self.open_folder_button.clicked.connect(self.open_saved_folder)
        button_layout.addWidget(self.open_folder_button)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        button_layout.addWidget(self.close_button)

        main_layout.addLayout(button_layout)
        self.on_format_changed()

    def add_row(self, layout, row):
        row.play_clicked.connect(self.toggle_playback)
        row.seek_requested.connect(self.seek)
        row.save_clicked.connect(self.save_stem)
        layout.addWidget(row)
        self.rows.append(row)

    # Playback ---------------------------------------------------------------

    def toggle_playback(self, row):
        """Play or pause a row. Another row continues from the current position."""
        if row is self.current_row:
            if self.pending_position is not None:
                # Still loading: decide what happens once the file is ready
                self.pending_play = not self.pending_play
                self.update_rows()
            elif self.is_playing():
                self.player.pause()
            else:
                self.player.play()
        else:
            self.switch_to(row, self.current_position(), play=True)

    def current_position(self):
        """Playback position in milliseconds, also while a file is still loading."""
        if self.pending_position is not None:
            return self.pending_position
        return self.player.position() if self.current_row else 0

    def seek(self, row, fraction):
        """Jump to a position (0.0 to 1.0) in a row."""
        position = int(fraction * self.duration_ms)
        if row is self.current_row:
            if self.pending_position is not None:
                # Still loading: applied as soon as the file is ready
                self.pending_position = position
            else:
                self.player.setPosition(position)
            self.on_position_changed(position)
        else:
            self.switch_to(row, position, play=self.is_playing() or self.current_row is None)

    def is_playing(self):
        """Whether audio is playing, or about to once the file has been loaded."""
        if self.pending_position is not None:
            return self.pending_play
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def switch_to(self, row, position, play):
        """Make a row the one that is played, starting at the given position."""
        self.current_row = row
        # The position can only be set once the new file has been loaded
        self.pending_position = position
        self.pending_play = play
        # Replacing the source first reports the previous file as loaded once
        # more; only the notifications after setSource() are about the new one
        self.switching_source = True
        self.player.setSource(QUrl.fromLocalFile(row.audio_file))
        self.switching_source = False
        self.update_rows()
        self.on_position_changed(position)

    def on_media_status_changed(self, status):
        if self.switching_source:
            return
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            if self.pending_position is not None:
                position, play = self.pending_position, self.pending_play
                self.pending_position = None
                if position:
                    self.player.setPosition(position)
                if play:
                    self.player.play()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            # Rewind when the end is reached
            self.player.stop()
            self.player.setPosition(0)
            self.on_position_changed(0)

    def on_position_changed(self, position):
        if self.pending_position is not None:
            # Still loading: show where playback is going to continue
            position = self.pending_position
        fraction = position / self.duration_ms if self.duration_ms else 0.0
        for row in self.rows:
            row.waveform.set_position(fraction)
        self.update_time_label(position)

    def on_playback_state_changed(self, state):
        self.update_rows()

    def on_player_error(self, error, message):
        if error != QMediaPlayer.Error.NoError:
            self.status_label.setText(f"Playback error: {message}")

    def on_volume_changed(self, value):
        self.audio_output.setVolume(value / 100.0)

    def update_rows(self):
        playing = self.is_playing()
        for row in self.rows:
            row.set_state(row is self.current_row, playing)

    def update_time_label(self, position):
        self.time_label.setText(f"{format_time(position / 1000)} / {format_time(self.duration_ms / 1000)}")

    def stop_playback(self):
        """Stop audio playback and release the audio file."""
        self.player.stop()
        self.player.setSource(QUrl())

    # Saving -----------------------------------------------------------------

    def export_choice(self):
        """The (format key, bitrate) selected for saving."""
        return self.format_combo.currentData(), self.bitrate_combo.currentData()

    def on_format_changed(self):
        fmt, bitrate = self.export_choice()
        self.bitrate_combo.setVisible(ffmpeg.EXPORT_FORMATS[fmt].lossy)
        # Remember the choice for next time
        self.settings.set("export_format", fmt)
        self.settings.set("export_bitrate", bitrate)

    def start_directory(self):
        last = self.settings.get("last_save_dir")
        return last if last and os.path.isdir(last) else os.path.dirname(str(self.result.source))

    def save_stem(self, row):
        """Save one stem to a user-selected location."""
        fmt, bitrate = self.export_choice()
        export_format = ffmpeg.EXPORT_FORMATS[fmt]
        default_name = paths.safe_name(f"{self.result.title} - {row.stem}") + export_format.extension
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Audio File", os.path.join(self.start_directory(), default_name),
            f"{export_format.label} (*{export_format.extension})"
        )
        if not file_path:
            return
        self.settings.set("last_save_dir", os.path.dirname(file_path))
        self.run_export(
            lambda: ffmpeg.export_audio(row.audio_file, file_path, fmt, bitrate),
            f"Saving {row.title.lower()}..."
        )

    def save_all_files(self):
        """Save all stems to a user-selected directory."""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Directory to Save All Files", self.start_directory()
        )
        if not dir_path:
            return
        self.settings.set("last_save_dir", dir_path)
        fmt, bitrate = self.export_choice()
        self.run_export(
            lambda: pipeline.export_result(self.result, dir_path, fmt, bitrate),
            "Saving all stems..."
        )

    def run_export(self, function, message):
        """Run an export in the background, keeping the window responsive."""
        if self.export_worker is not None:
            return
        self.set_export_enabled(False)
        self.open_folder_button.setVisible(False)
        self.status_label.setText(message)
        self.export_worker = FunctionWorker(function, self)
        self.export_worker.succeeded.connect(self.on_export_succeeded)
        self.export_worker.failed.connect(self.on_export_failed)
        self.export_worker.finished.connect(self.on_export_done)
        self.export_worker.start()

    def on_export_succeeded(self, saved_path):
        saved_path = str(saved_path)
        self.saved_folder = saved_path if os.path.isdir(saved_path) else os.path.dirname(saved_path)
        self.status_label.setText(f"Saved to {saved_path}")
        self.status_label.setToolTip(saved_path)
        self.open_folder_button.setVisible(True)

    def on_export_failed(self, message):
        self.status_label.setText("Saving failed")
        QMessageBox.critical(self, "Saving Failed", f"The audio could not be saved:\n{message}")

    def on_export_done(self):
        self.export_worker = None
        self.set_export_enabled(True)

    def set_export_enabled(self, enabled):
        self.save_all_button.setEnabled(enabled)
        for row in self.rows:
            if row.stem is not None:
                row.save_button.setEnabled(enabled)

    def open_saved_folder(self):
        if self.saved_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.saved_folder))

    def done(self, result):
        """Called however the window is closed (button, Escape or title bar)."""
        # Let a running export finish so no half-written file is left behind
        if self.export_worker is not None:
            self.export_worker.wait()
        self.stop_playback()
        # Waveforms still being read keep their files open, which would
        # prevent deleting the working files
        QThreadPool.globalInstance().waitForDone(5000)
        super().done(result)
