import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QFileDialog,
    QProgressBar, QMessageBox, QCheckBox, QApplication,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import Qt

from core import ffmpeg, paths, pipeline
from core.audio import format_time
from core.settings import Settings
from models import registry
from ui.drop_area import DropArea
from ui.model_selection_dialog import ModelSelectionDialog
from ui.manage_models_dialog import ManageModelsDialog
from ui.results_window import ResultsWindow
from ui.settings_dialog import SettingsDialog
from ui.styles.dark_mode import apply_theme
from ui.workers import BatchWorker, ProbeWorker


class Job:
    """An audio file in the processing queue."""

    CHECKING = "checking"
    PENDING = "pending"
    INVALID = "invalid"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def __init__(self, job_id, path):
        self.id = job_id
        self.path = path
        self.duration = None
        self.state = Job.CHECKING
        # The separation result and the model settings that produced it
        self.result = None
        self.result_key = None
        self.error = ""
        self.saved_to = ""
        self.item = None


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.setWindowTitle("CaptainStems")
        self.setMinimumSize(860, 640)

        self.settings = settings if settings is not None else Settings()

        # Create model instances: the default model of each family, plus the
        # models the user added through the advanced selection
        self.models = {}
        for identifier in registry.default_model_ids() + self.settings.custom_models():
            if identifier not in self.models and registry.parse_model_id(identifier):
                self.models[identifier] = registry.create_model(identifier)

        self.current_model_id = None
        self.current_model = None
        self.jobs = {}
        self.next_job_id = 1
        self.worker = None
        self.batch_job_ids = []
        self.batch_done = 0
        self.batch_key = None
        self.current_status = ""
        self.closing = False
        self.probe_workers = []
        self.results_windows = []
        self.session_dir = None

        self.init_ui()
        paths.clean_stale_sessions()

    def init_ui(self):
        # Main layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        layout = QVBoxLayout(main_widget)

        # Title
        title_label = QLabel("CaptainStems")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Shown only if no FFmpeg binary is available at all
        self.ffmpeg_warning = QLabel(
            "<b>FFmpeg was not found.</b> Audio files cannot be read without it. "
            f"Install it with: <code>{ffmpeg.install_hint()}</code>"
        )
        self.ffmpeg_warning.setWordWrap(True)
        self.ffmpeg_warning.setVisible(ffmpeg.find_ffmpeg() is None)
        layout.addWidget(self.ffmpeg_warning)

        # Model selection
        model_layout = QHBoxLayout()
        model_label = QLabel("Model:")
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(260)
        for identifier in self.models:
            self.model_combo.addItem("", identifier)
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)

        # Advanced model selection button
        self.advanced_model_button = QPushButton("Advanced Models...")
        self.advanced_model_button.clicked.connect(self.show_advanced_model_selection)

        # Add manage models button
        self.manage_models_button = QPushButton("Manage Models...")
        self.manage_models_button.clicked.connect(self.show_manage_models_dialog)

        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_combo)
        model_layout.addWidget(self.advanced_model_button)
        model_layout.addWidget(self.manage_models_button)

        # Add install button
        self.install_button = QPushButton("Install Model")
        self.install_button.setVisible(False)
        self.install_button.clicked.connect(self.install_model)
        model_layout.addWidget(self.install_button)

        # Add remove button
        self.remove_button = QPushButton("Remove Model")
        self.remove_button.setVisible(False)
        self.remove_button.clicked.connect(self.remove_model)
        model_layout.addWidget(self.remove_button)

        model_layout.addStretch()

        self.settings_button = QPushButton("Settings...")
        self.settings_button.clicked.connect(self.show_settings)
        model_layout.addWidget(self.settings_button)

        layout.addLayout(model_layout)

        # Option for two-stems mode (vocals/instrumental)
        options_layout = QHBoxLayout()
        self.two_stems_checkbox = QCheckBox("Separate into vocals/instrumental only")
        self.two_stems_checkbox.setChecked(self.settings.get("two_stems"))
        self.two_stems_checkbox.toggled.connect(self.on_two_stems_toggled)
        options_layout.addWidget(self.two_stems_checkbox)
        options_layout.addStretch()
        self.stems_label = QLabel()
        self.stems_label.setEnabled(False)
        options_layout.addWidget(self.stems_label)
        layout.addLayout(options_layout)

        # Drop area
        self.drop_area = DropArea()
        self.drop_area.files_dropped.connect(self.add_files)
        self.drop_area.browse_requested.connect(self.browse_files)
        layout.addWidget(self.drop_area, 1)

        # Queue of files to process
        self.queue_tree = QTreeWidget()
        self.queue_tree.setHeaderLabels(["File", "Length", "Status"])
        self.queue_tree.setRootIsDecorated(False)
        self.queue_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.queue_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.queue_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.queue_tree.header().setStretchLastSection(False)
        self.queue_tree.setColumnWidth(2, 260)
        self.queue_tree.itemDoubleClicked.connect(self.on_queue_item_activated)
        self.queue_tree.itemSelectionChanged.connect(self.update_ui_state)
        self.queue_tree.setVisible(False)
        layout.addWidget(self.queue_tree, 3)

        queue_buttons = QHBoxLayout()
        self.add_button = QPushButton("Add Files...")
        self.add_button.clicked.connect(self.browse_files)
        queue_buttons.addWidget(self.add_button)
        self.remove_files_button = QPushButton("Remove")
        self.remove_files_button.clicked.connect(self.remove_selected_files)
        queue_buttons.addWidget(self.remove_files_button)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_queue)
        queue_buttons.addWidget(self.clear_button)
        queue_buttons.addStretch()
        self.view_results_button = QPushButton("View Results")
        self.view_results_button.clicked.connect(self.view_selected_results)
        queue_buttons.addWidget(self.view_results_button)
        layout.addLayout(queue_buttons)

        # Status and progress
        self.status_label = QLabel()
        # File names may contain characters that mean something in HTML
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_processing)
        progress_layout.addWidget(self.cancel_button)
        layout.addLayout(progress_layout)

        # Bottom buttons
        button_layout = QHBoxLayout()

        self.process_button = QPushButton("Process Audio")
        self.process_button.setEnabled(False)
        self.process_button.setDefault(True)
        self.process_button.clicked.connect(self.process_audio)

        button_layout.addStretch()
        button_layout.addWidget(self.process_button)

        layout.addLayout(button_layout)

        # Initialize with the model used last time
        self.refresh_model_labels()
        index = self.model_combo.findData(self.settings.get("last_model"))
        if index > 0:
            self.model_combo.setCurrentIndex(index)
        else:
            self.on_model_changed(0)

    # Models -----------------------------------------------------------------

    def refresh_model_labels(self):
        """Update the combo box texts to reflect which models are installed."""
        for index in range(self.model_combo.count()):
            identifier = self.model_combo.itemData(index)
            display_name = registry.display_name(identifier)
            if not self.models[identifier].available:
                display_name += " (not installed)"
            self.model_combo.setItemText(index, display_name)

    def refresh_availability(self):
        """Re-check which models are installed, after installing or uninstalling."""
        for model in self.models.values():
            model.available = model.check_dependencies()
        self.refresh_model_labels()
        self.update_model_controls()
        self.update_ui_state()

    def add_model(self, identifier):
        """Add a model to the selection list and remember it."""
        if identifier in self.models:
            return
        self.models[identifier] = registry.create_model(identifier)
        self.model_combo.addItem("", identifier)
        self.refresh_model_labels()
        custom = self.settings.custom_models()
        if identifier not in custom and not registry.is_default(identifier):
            self.settings.set("custom_models", custom + [identifier])

    def show_advanced_model_selection(self):
        # Use the advanced model selection dialog
        identifier = ModelSelectionDialog.get_model(self, self.current_model_id)

        if identifier:
            self.add_model(identifier)

            # Select the model
            index = self.model_combo.findData(identifier)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)

    def show_manage_models_dialog(self):
        """
        Shows a dialog for managing (installing, uninstalling, removing) models.
        """
        custom = [identifier for identifier in self.models if not registry.is_default(identifier)]
        dialog = ManageModelsDialog(self, custom)
        dialog.models_removed.connect(self.remove_models_batch)
        dialog.backends_changed.connect(self.refresh_availability)
        dialog.exec()
        self.refresh_availability()

    def remove_models_batch(self, models_to_remove):
        """Remove multiple models from the selection list at once."""
        for identifier in models_to_remove:
            if identifier not in self.models or registry.is_default(identifier):
                continue
            index = self.model_combo.findData(identifier)
            if index >= 0:
                # Remove from combo box (selects a neighbor if it was current)
                self.model_combo.removeItem(index)
            # Remove from models dictionary
            self.models.pop(identifier)

        self.settings.set(
            "custom_models",
            [identifier for identifier in self.settings.custom_models() if identifier not in models_to_remove]
        )
        self.on_model_changed(self.model_combo.currentIndex())

    def on_model_changed(self, index):
        identifier = self.model_combo.itemData(index)
        self.current_model_id = identifier
        self.current_model = self.models.get(identifier)
        if identifier:
            self.settings.set("last_model", identifier)

        self.update_model_controls()

        # Update UI state to reflect current model and file status
        self.update_ui_state()

    def update_model_controls(self):
        """Update the widgets that depend on the selected model."""
        model = self.current_model
        if model is None:
            self.install_button.setVisible(False)
            self.remove_button.setVisible(False)
            self.two_stems_checkbox.setEnabled(False)
            self.stems_label.setText("")
            return

        # Check if model is available
        self.install_button.setVisible(not model.available)

        # Show remove button for non-default models
        self.remove_button.setVisible(not registry.is_default(self.current_model_id))

        # Update two-stems checkbox based on model
        if model.supports_two_stems:
            self.two_stems_checkbox.setEnabled(True)
            self.two_stems_checkbox.setToolTip("Separate into vocals and instrumental only")
        else:
            self.two_stems_checkbox.setEnabled(False)
            if len(model.get_stems()) == 2:
                self.two_stems_checkbox.setToolTip("This model already produces two stems")
            else:
                self.two_stems_checkbox.setToolTip("Two-stems mode is only available for Demucs models")

        stems = pipeline.sort_stems(model.get_stems(self.two_stems()))
        self.stems_label.setText("Stems: " + ", ".join(stems))

    def two_stems(self):
        """Whether two-stems mode applies to the selected model."""
        return (
            self.current_model is not None
            and self.current_model.supports_two_stems
            and self.two_stems_checkbox.isChecked()
        )

    def on_two_stems_toggled(self, checked):
        self.settings.set("two_stems", checked)
        self.update_model_controls()
        self.update_ui_state()

    def install_model(self):
        if not self.current_model:
            return

        # Installs into the model's own environment, showing the installer output
        ManageModelsDialog.install_backend(self, self.current_model)
        self.refresh_availability()

    def remove_model(self):
        if not self.current_model or registry.is_default(self.current_model_id):
            return

        display_name = registry.display_name(self.current_model_id)

        # Confirm removal
        confirmation = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Are you sure you want to remove the model '{display_name}'?\n\n"
            "This will only remove it from the selection list, not from your system.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if confirmation == QMessageBox.StandardButton.Yes:
            self.remove_models_batch([self.current_model_id])

    def show_settings(self):
        dialog = SettingsDialog(self, self.settings)
        if dialog.exec():
            apply_theme(QApplication.instance(), self.settings.theme())
            self.update_ui_state()

    # Queue ------------------------------------------------------------------

    def browse_files(self):
        if self.is_processing():
            return
        last = self.settings.get("last_open_dir")
        start = last if last and os.path.isdir(last) else os.path.expanduser("~")
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Audio Files", start, DropArea.file_dialog_filter()
        )
        if files:
            self.settings.set("last_open_dir", os.path.dirname(files[0]))
            self.add_files(files)

    def add_files(self, files):
        """Add audio files to the queue and validate them in the background."""
        if self.is_processing():
            return
        known = {os.path.normcase(job.path) for job in self.jobs.values()}
        added = []
        for path in files:
            path = os.path.normpath(path)
            if os.path.normcase(path) in known:
                continue
            known.add(os.path.normcase(path))
            job = Job(self.next_job_id, path)
            self.next_job_id += 1
            job.item = QTreeWidgetItem([os.path.basename(path), "", ""])
            job.item.setData(0, Qt.ItemDataRole.UserRole, job.id)
            job.item.setToolTip(0, path)
            self.queue_tree.addTopLevelItem(job.item)
            self.jobs[job.id] = job
            self.update_job_row(job)
            added.append(path)

        if added:
            # Reading the duration proves a file really contains audio
            probe = ProbeWorker(added, self)
            probe.probed.connect(self.on_file_probed)
            probe.finished.connect(lambda probe=probe: self.probe_workers.remove(probe))
            self.probe_workers.append(probe)
            probe.start()
        self.update_ui_state()

    def on_file_probed(self, path, duration):
        for job in self.jobs.values():
            if job.path == path and job.state == Job.CHECKING:
                if duration > 0:
                    job.duration = duration
                    job.state = Job.PENDING
                else:
                    job.state = Job.INVALID
                    job.error = "Not a readable audio file"
                self.update_job_row(job)
        self.update_ui_state()

    def update_job_row(self, job, detail=None):
        """Refresh the queue row of a job."""
        texts = {
            Job.CHECKING: "Checking...",
            Job.PENDING: "Ready",
            Job.INVALID: job.error,
            Job.PROCESSING: detail or "Processing...",
            Job.FAILED: "Failed",
            Job.CANCELLED: "Cancelled",
        }
        if job.state == Job.DONE:
            text = f"Done ({job.result.model_label})"
            if job.saved_to:
                text += ", saved"
            elif job.error:
                text += ", not saved"
        else:
            text = texts[job.state]
        job.item.setText(1, format_time(job.duration) if job.duration else "")
        job.item.setText(2, text)

        if job.state == Job.DONE and job.saved_to:
            tooltip = f"Saved to {job.saved_to}\nDouble-click to view the stems"
        elif job.state == Job.DONE:
            tooltip = (job.error + "\n" if job.error else "") + "Double-click to view the stems"
        else:
            tooltip = job.error
        job.item.setToolTip(2, tooltip)

    def selected_jobs(self):
        return [self.jobs[item.data(0, Qt.ItemDataRole.UserRole)] for item in self.queue_tree.selectedItems()]

    def remove_jobs(self, jobs):
        for job in jobs:
            # Results shown in an open window stay until the application exits
            if job.result is not None and not self.is_result_open(job.result):
                job.result.discard()
            self.queue_tree.takeTopLevelItem(self.queue_tree.indexOfTopLevelItem(job.item))
            self.jobs.pop(job.id, None)
        self.update_ui_state()

    def remove_selected_files(self):
        if not self.is_processing():
            self.remove_jobs(self.selected_jobs())

    def clear_queue(self):
        if not self.is_processing():
            self.remove_jobs(list(self.jobs.values()))

    def result_key(self):
        """Identifies the model settings a result was produced with."""
        return f"{self.current_model_id}|{self.two_stems()}"

    def jobs_to_process(self):
        """Jobs that have no result for the selected model yet."""
        key = self.result_key()
        return [
            job for job in self.jobs.values()
            if job.state in (Job.PENDING, Job.FAILED, Job.CANCELLED)
            or (job.state == Job.DONE and job.result_key != key)
        ]

    def is_processing(self):
        return self.worker is not None

    def update_ui_state(self):
        processing = self.is_processing()

        # Check model availability
        model_available = self.current_model is not None and self.current_model.available

        has_jobs = bool(self.jobs)
        pending = self.jobs_to_process()

        # Check if we can process
        can_process = model_available and bool(pending) and not processing

        # Enable or disable the process button
        self.process_button.setEnabled(can_process)
        if len(pending) > 1:
            self.process_button.setText(f"Process {len(pending)} Files")
        else:
            self.process_button.setText("Process Audio")

        # The queue takes over the window once it has entries
        self.queue_tree.setVisible(has_jobs)
        self.drop_area.setMaximumHeight(110 if has_jobs else 16777215)

        selected = self.selected_jobs()
        self.add_button.setEnabled(not processing)
        self.remove_files_button.setEnabled(bool(selected) and not processing)
        self.clear_button.setEnabled(has_jobs and not processing)
        self.view_results_button.setEnabled(any(job.result is not None for job in selected))

        # Models cannot be switched or changed while they are in use
        for widget in (self.model_combo, self.advanced_model_button, self.manage_models_button,
                       self.install_button, self.remove_button, self.settings_button):
            widget.setEnabled(not processing)
        self.two_stems_checkbox.setEnabled(
            not processing and self.current_model is not None and self.current_model.supports_two_stems
        )

        # Update drop area message based on state
        if self.current_model is not None and not model_available:
            # Model not installed
            self.drop_area.set_message("Model not installed", "Click 'Install Model' first")
        elif has_jobs:
            self.drop_area.set_message("Drag more audio files here")
        else:
            self.drop_area.set_message("Drag audio files here", "or click to browse. Folders work too")

    # Processing -------------------------------------------------------------

    def process_audio(self):
        jobs = self.jobs_to_process()
        if not self.current_model or not jobs or self.is_processing():
            return

        if self.session_dir is None or not os.path.isdir(self.session_dir):
            try:
                self.session_dir = paths.new_session_dir()
            except OSError as e:
                QMessageBox.critical(
                    self,
                    "Processing Error",
                    f"The temporary working directory could not be created:\n{e}"
                )
                return

        export = None
        if self.settings.get("auto_save"):
            # An empty output folder means: next to each source file
            export = (
                self.settings.get("output_dir") or None,
                self.settings.export_format(),
                self.settings.export_bitrate(),
            )

        for job in jobs:
            # A result for other model settings is replaced
            if job.result is not None and not self.is_result_open(job.result):
                job.result.discard()
            job.result = None
            job.error = ""
            job.saved_to = ""
            job.state = Job.PENDING
            self.update_job_row(job)

        self.batch_job_ids = [job.id for job in jobs]
        self.batch_done = 0
        self.batch_key = self.result_key()

        self.worker = BatchWorker(
            [(job.id, job.path) for job in jobs],
            self.current_model,
            registry.display_name(self.current_model_id),
            self.session_dir,
            two_stems=self.two_stems(),
            options=self.settings.processing_options(),
            export=export,
            parent=self,
        )
        self.worker.job_started.connect(self.on_job_started)
        self.worker.job_progress.connect(self.on_job_progress)
        self.worker.job_status.connect(self.on_job_status)
        self.worker.job_finished.connect(self.on_job_finished)
        self.worker.job_failed.connect(self.on_job_failed)
        self.worker.batch_finished.connect(self.on_batch_finished)

        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setVisible(True)
        self.status_label.setText("Starting...")
        self.update_ui_state()
        self.worker.start()

    def cancel_processing(self):
        if self.worker is not None:
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Cancelling...")
            self.worker.cancel()

    def on_job_started(self, job_id):
        job = self.jobs.get(job_id)
        if job is None:
            return
        job.state = Job.PROCESSING
        self.current_status = "Processing..."
        self.update_job_row(job)
        self.queue_tree.scrollToItem(job.item)
        self.update_batch_status(job)

    def on_job_progress(self, job_id, value):
        job = self.jobs.get(job_id)
        if job is None:
            return
        total = max(1, len(self.batch_job_ids))
        self.progress_bar.setValue(int((self.batch_done * 100 + value) / total))
        self.update_job_row(job, f"{self.current_status} {value}%")

    def on_job_status(self, job_id, text):
        job = self.jobs.get(job_id)
        if job is None:
            return
        self.current_status = text
        self.update_job_row(job, text)
        self.update_batch_status(job)

    def update_batch_status(self, job):
        total = len(self.batch_job_ids)
        prefix = f"File {self.batch_done + 1} of {total}: " if total > 1 else ""
        self.status_label.setText(f"{prefix}{os.path.basename(job.path)} - {self.current_status}")

    def on_job_finished(self, job_id, result, saved_to, save_error):
        self.batch_done += 1
        job = self.jobs.get(job_id)
        if job is None:
            result.discard()
            return
        job.state = Job.DONE
        job.result = result
        job.result_key = self.batch_key
        job.saved_to = saved_to
        job.error = f"Stems could not be saved: {save_error}" if save_error else ""
        self.update_job_row(job)

    def on_job_failed(self, job_id, error_message):
        self.batch_done += 1
        job = self.jobs.get(job_id)
        if job is None:
            return
        job.state = Job.FAILED
        job.error = error_message
        self.update_job_row(job)

    def on_batch_finished(self, cancelled):
        if self.closing or self.worker is None:
            return
        self.worker.wait()
        self.worker = None
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)

        batch = [self.jobs[job_id] for job_id in self.batch_job_ids if job_id in self.jobs]
        for job in batch:
            if job.state in (Job.PROCESSING, Job.PENDING) and cancelled:
                job.state = Job.CANCELLED
                self.update_job_row(job)

        done = [job for job in batch if job.state == Job.DONE]
        failed = [job for job in batch if job.state == Job.FAILED]
        unsaved = [job for job in done if job.error]

        if cancelled:
            summary = f"Cancelled. {len(done)} of {len(batch)} files were separated."
        elif len(batch) == 1 and done:
            summary = "Separation complete."
            if done[0].saved_to:
                summary += f" Stems saved to {done[0].saved_to}"
        else:
            summary = f"{len(done)} of {len(batch)} files separated."
            if failed:
                summary += f" {len(failed)} failed."
        if done and not (len(batch) == 1 and done[0].saved_to):
            summary += " Double-click a file to view its stems."
        self.status_label.setText(summary)
        self.update_ui_state()

        if failed:
            details = "\n\n".join(f"{os.path.basename(job.path)}:\n{job.error}" for job in failed[:3])
            if len(failed) > 3:
                details += f"\n\n... and {len(failed) - 3} more"
            QMessageBox.critical(
                self,
                "Processing Error",
                f"An error occurred during audio separation:\n\n{details}"
            )
        if unsaved:
            QMessageBox.warning(
                self,
                "Saving Failed",
                "The stems of these files could not be saved automatically:\n\n"
                + "\n".join(f"{os.path.basename(job.path)}: {job.error}" for job in unsaved[:5])
                + "\n\nOpen their results to save them manually."
            )

        # Show the results window with processed stems
        if len(batch) == 1 and done and not cancelled and self.settings.get("open_results"):
            self.show_results(done[0])

    # Results ----------------------------------------------------------------

    def is_result_open(self, result):
        return any(window.result is result for window in self.results_windows)

    def show_results(self, job):
        if job.result is None:
            return
        for window in self.results_windows:
            if window.result is job.result:
                window.raise_()
                window.activateWindow()
                return
        window = ResultsWindow(self, job.result, self.settings)
        window.finished.connect(lambda _result, window=window: self.on_results_closed(window))
        self.results_windows.append(window)
        window.show()

    def on_results_closed(self, window):
        if window in self.results_windows:
            self.results_windows.remove(window)
        window.deleteLater()

    def on_queue_item_activated(self, item, _column):
        job = self.jobs.get(item.data(0, Qt.ItemDataRole.UserRole))
        if job is None:
            return
        if job.result is not None:
            self.show_results(job)
        elif job.state == Job.FAILED and job.error:
            QMessageBox.critical(self, "Processing Error", job.error)

    def view_selected_results(self):
        for job in self.selected_jobs():
            self.show_results(job)

    def closeEvent(self, event):
        if self.is_processing():
            confirmation = QMessageBox.question(
                self,
                "Processing in Progress",
                "Audio is still being processed. Cancel it and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if confirmation != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        self.closing = True
        # The batch may have finished while the question was showing
        worker = self.worker
        if worker is not None:
            worker.cancel()
            worker.wait()
        for probe in list(self.probe_workers):
            probe.stop_requested = True
            probe.wait()

        # Close the results windows first: they keep audio files open
        for window in list(self.results_windows):
            window.done(0)

        self.settings.sync()
        if self.session_dir is not None:
            paths.remove_tree(self.session_dir)
        event.accept()
