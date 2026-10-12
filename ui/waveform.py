import numpy as np
from PyQt6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import QSizePolicy, QWidget

from core.audio import compute_peaks


class _PeakSignals(QObject):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)


class _PeakLoader(QRunnable):
    """Computes the waveform envelope of a file on a worker thread."""

    def __init__(self, path, buckets):
        super().__init__()
        self.path = path
        self.buckets = buckets
        self.signals = _PeakSignals()

    def run(self):
        try:
            peaks = compute_peaks(self.path, self.buckets)
        except Exception as e:
            self.signals.failed.emit(str(e))
        else:
            self.signals.loaded.emit(peaks)


class WaveformView(QWidget):
    """
    Displays the waveform of an audio file with a playback position.
    Clicking or dragging on the waveform requests a seek.
    """

    # Position between 0.0 and 1.0
    seek_requested = pyqtSignal(float)

    BUCKETS = 2000

    def __init__(self, audio_file, parent=None):
        super().__init__(parent)
        self.audio_file = audio_file
        self.peaks = None
        self.error = None
        self.position = 0.0
        self.active = False
        # Rendered waveforms, reused until size, colors or data change
        self._cache_key = None
        self._cache = {}

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(70)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Keep a reference to the signals: the runnable itself is owned by the pool
        loader = _PeakLoader(audio_file, self.BUCKETS)
        self._signals = loader.signals
        self._signals.loaded.connect(self._on_loaded)
        self._signals.failed.connect(self._on_failed)
        QThreadPool.globalInstance().start(loader)

    def sizeHint(self):
        return QSize(600, 80)

    def _on_loaded(self, peaks):
        self.peaks = peaks
        self._cache_key = None
        self.update()

    def _on_failed(self, message):
        self.error = message
        self.update()

    def set_position(self, fraction):
        """Move the playback position (0.0 to 1.0)."""
        fraction = min(1.0, max(0.0, fraction))
        if fraction != self.position:
            self.position = fraction
            # Only the active waveform shows the position
            if self.active:
                self.update()

    def set_active(self, active):
        """Highlight the waveform of the stem that is currently selected for playback."""
        if active != self.active:
            self.active = active
            self.update()

    def _column_envelope(self, width):
        """Minimum and maximum of the waveform for each pixel column."""
        edges = np.linspace(0, len(self.peaks), width + 1).astype(int)
        starts = np.minimum(edges[:-1], len(self.peaks) - 1)
        # reduceat covers [start, next start); columns narrower than a bucket repeat it
        low = np.minimum.reduceat(self.peaks[:, 0], starts)
        high = np.maximum.reduceat(self.peaks[:, 1], starts)
        return low, high

    def _render(self, color):
        """Draw the whole waveform in one color into an image."""
        ratio = self.devicePixelRatioF()
        width, height = self.width(), self.height()
        pixmap = QPixmap(int(width * ratio), int(height * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)

        low, high = self._column_envelope(width)
        middle = height / 2.0
        scale = (height / 2.0) - 2
        tops = (middle - high * scale).astype(int)
        bottoms = np.maximum((middle - low * scale).astype(int), tops + 1)

        painter = QPainter(pixmap)
        painter.setPen(color)
        for x in range(width):
            painter.drawLine(x, int(tops[x]), x, int(bottoms[x]))
        painter.end()
        return pixmap

    def _waveforms(self):
        """The waveform images for the current size and colors: (unplayed, played)."""
        palette = self.palette()
        text_color = palette.color(QPalette.ColorRole.Text)
        accent = palette.color(QPalette.ColorRole.Highlight)
        key = (self.width(), self.height(), self.devicePixelRatioF(), text_color.rgba(), accent.rgba())
        if key != self._cache_key:
            idle = QColor(text_color)
            idle.setAlpha(110)
            upcoming = QColor(accent)
            upcoming.setAlpha(120)
            self._cache = {
                "idle": self._render(idle),
                "upcoming": self._render(upcoming),
                "played": self._render(accent),
            }
            self._cache_key = key
        return self._cache

    def paintEvent(self, event):
        painter = QPainter(self)
        palette = self.palette()
        width, height = self.width(), self.height()
        painter.fillRect(self.rect(), palette.color(QPalette.ColorRole.Base))

        text_color = palette.color(QPalette.ColorRole.Text)
        if self.peaks is None or len(self.peaks) == 0:
            painter.setPen(text_color)
            message = "Could not read audio" if self.error else (
                "Loading waveform..." if self.peaks is None else "Empty audio file")
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, message)
            return
        if width <= 0 or height <= 0:
            return

        images = self._waveforms()
        if not self.active:
            painter.drawPixmap(0, 0, images["idle"])
            return

        # The part before the playback position in full color, the rest dimmed
        playhead = int(self.position * width)
        painter.drawPixmap(0, 0, images["upcoming"])
        painter.setClipRect(0, 0, playhead, height)
        painter.drawPixmap(0, 0, images["played"])
        painter.setClipping(False)
        painter.setPen(QPen(text_color, 1))
        painter.drawLine(playhead, 0, playhead, height)

    def _seek_to(self, x):
        if self.width() > 0:
            self.seek_requested.emit(min(1.0, max(0.0, x / self.width())))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._seek_to(event.position().x())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._seek_to(event.position().x())
