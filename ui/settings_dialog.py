import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QLineEdit, QFileDialog, QDialogButtonBox,
    QMessageBox
)
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

from core import ffmpeg, paths
from core.envs import has_nvidia_gpu


class SettingsDialog(QDialog):
    """Dialog for editing the application preferences."""

    THEME_LABELS = {"system": "Follow system", "dark": "Dark", "light": "Light"}
    DEVICE_LABELS = {
        "auto": "Automatic (GPU if available)",
        "cpu": "CPU only",
        "cuda": "NVIDIA GPU (CUDA)",
        "mps": "Apple GPU (MPS)",
    }

    def __init__(self, parent, settings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self.init_ui()
        self.load()

    def init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)

        # Appearance
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout(appearance_group)
        self.theme_combo = QComboBox()
        for key, label in self.THEME_LABELS.items():
            self.theme_combo.addItem(label, key)
        appearance_layout.addRow("Theme:", self.theme_combo)
        layout.addWidget(appearance_group)

        # Saving
        export_group = QGroupBox("Saving stems")
        export_layout = QFormLayout(export_group)

        self.format_combo = QComboBox()
        for key, export_format in ffmpeg.EXPORT_FORMATS.items():
            self.format_combo.addItem(export_format.label, key)
        self.format_combo.currentIndexChanged.connect(self.update_enabled)
        export_layout.addRow("Format:", self.format_combo)

        self.bitrate_combo = QComboBox()
        for bitrate in ffmpeg.BITRATES:
            self.bitrate_combo.addItem(bitrate.replace("k", " kbps"), bitrate)
        export_layout.addRow("Bitrate:", self.bitrate_combo)

        self.auto_save_checkbox = QCheckBox("Save stems automatically after processing")
        self.auto_save_checkbox.setToolTip(
            "Stems are written to a folder per track inside the output folder")
        self.auto_save_checkbox.toggled.connect(self.update_enabled)
        export_layout.addRow(self.auto_save_checkbox)

        output_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("Next to each source file")
        output_layout.addWidget(self.output_dir_edit)
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_output_dir)
        output_layout.addWidget(self.browse_button)
        export_layout.addRow("Output folder:", output_layout)

        self.open_results_checkbox = QCheckBox("Open the results window after processing a single file")
        export_layout.addRow(self.open_results_checkbox)
        layout.addWidget(export_group)

        # Processing
        processing_group = QGroupBox("Processing")
        processing_layout = QFormLayout(processing_group)

        self.device_combo = QComboBox()
        for key, label in self.DEVICE_LABELS.items():
            self.device_combo.addItem(label, key)
        processing_layout.addRow("Device:", self.device_combo)
        gpu_text = "NVIDIA GPU detected" if has_nvidia_gpu() else "No NVIDIA GPU detected"
        gpu_label = QLabel(gpu_text)
        gpu_label.setEnabled(False)
        processing_layout.addRow("", gpu_label)

        self.shifts_spin = QSpinBox()
        self.shifts_spin.setRange(1, 10)
        self.shifts_spin.setToolTip(
            "Number of random shifts averaged by Demucs. Higher values improve quality "
            "slightly and multiply the processing time.")
        processing_layout.addRow("Demucs shifts:", self.shifts_spin)

        self.overlap_spin = QDoubleSpinBox()
        self.overlap_spin.setRange(0.05, 0.9)
        self.overlap_spin.setSingleStep(0.05)
        self.overlap_spin.setDecimals(2)
        self.overlap_spin.setToolTip("Overlap between the chunks Demucs splits the audio into")
        processing_layout.addRow("Demucs overlap:", self.overlap_spin)

        self.mwf_checkbox = QCheckBox("Use multichannel Wiener filtering for Spleeter (slower, cleaner)")
        processing_layout.addRow(self.mwf_checkbox)
        layout.addWidget(processing_group)

        # Storage
        storage_group = QGroupBox("Storage")
        storage_layout = QVBoxLayout(storage_group)
        data_dir = paths.app_data_dir()
        storage_label = QLabel(f"Models are installed in:\n{data_dir}")
        storage_label.setWordWrap(True)
        storage_layout.addWidget(storage_label)
        storage_buttons = QHBoxLayout()
        open_data_button = QPushButton("Open Folder")
        open_data_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir))))
        storage_buttons.addWidget(open_data_button)
        storage_buttons.addStretch()
        storage_layout.addLayout(storage_buttons)
        layout.addWidget(storage_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self.restore_defaults)
        layout.addWidget(buttons)

    @staticmethod
    def select(combo, value):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def load(self, values=None):
        """Fill the widgets from the stored settings (or the given values)."""
        get = (lambda key: values[key]) if values is not None else self.settings.get
        self.select(self.theme_combo, get("theme"))
        self.select(self.format_combo, get("export_format"))
        self.select(self.bitrate_combo, get("export_bitrate"))
        self.auto_save_checkbox.setChecked(get("auto_save"))
        self.output_dir_edit.setText(get("output_dir"))
        self.open_results_checkbox.setChecked(get("open_results"))
        self.select(self.device_combo, get("device"))
        self.shifts_spin.setValue(get("demucs_shifts"))
        self.overlap_spin.setValue(get("demucs_overlap"))
        self.mwf_checkbox.setChecked(get("spleeter_mwf"))
        self.update_enabled()

    def restore_defaults(self):
        from core.settings import DEFAULTS
        self.load(DEFAULTS)

    def update_enabled(self):
        fmt = self.format_combo.currentData()
        self.bitrate_combo.setEnabled(ffmpeg.EXPORT_FORMATS[fmt].lossy)
        auto_save = self.auto_save_checkbox.isChecked()
        self.output_dir_edit.setEnabled(auto_save)
        self.browse_button.setEnabled(auto_save)

    def browse_output_dir(self):
        start = self.output_dir_edit.text() or os.path.expanduser("~")
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if dir_path:
            self.output_dir_edit.setText(dir_path)

    def accept(self):
        """Validate and store the settings."""
        output_dir = self.output_dir_edit.text().strip()
        if self.auto_save_checkbox.isChecked() and output_dir and not os.path.isdir(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as e:
                QMessageBox.warning(self, "Output Folder", f"The output folder cannot be created:\n{e}")
                return

        self.settings.set("theme", self.theme_combo.currentData())
        self.settings.set("export_format", self.format_combo.currentData())
        self.settings.set("export_bitrate", self.bitrate_combo.currentData())
        self.settings.set("auto_save", self.auto_save_checkbox.isChecked())
        self.settings.set("output_dir", output_dir)
        self.settings.set("open_results", self.open_results_checkbox.isChecked())
        self.settings.set("device", self.device_combo.currentData())
        self.settings.set("demucs_shifts", self.shifts_spin.value())
        self.settings.set("demucs_overlap", round(self.overlap_spin.value(), 2))
        self.settings.set("spleeter_mwf", self.mwf_checkbox.isChecked())
        self.settings.sync()
        super().accept()
