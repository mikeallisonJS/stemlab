"""Background threads that keep long-running work off the user interface thread."""

import os
import threading
import traceback

from PyQt6.QtCore import QThread, pyqtSignal

from core import ffmpeg, pipeline
from core.process import ProcessCancelled


class FunctionWorker(QThread):
    """Runs a function on a background thread and reports its outcome."""

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            result = self.function()
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e) or type(e).__name__)
        else:
            self.succeeded.emit(result)


class ProbeWorker(QThread):
    """Reads the duration of audio files to validate them."""

    # path, duration in seconds (negative if the file is not readable audio)
    probed = pyqtSignal(str, float)

    def __init__(self, files, parent=None):
        super().__init__(parent)
        self.files = list(files)
        self.stop_requested = False

    def run(self):
        for path in self.files:
            if self.stop_requested:
                return
            duration = ffmpeg.media_duration(path)
            self.probed.emit(path, duration if duration and duration > 0 else -1.0)


class InstallWorker(QThread):
    """Installs or uninstalls the backend of a model."""

    log = pyqtSignal(str)
    # success, error message
    done = pyqtSignal(bool, str)

    def __init__(self, model, uninstall=False, parent=None):
        super().__init__(parent)
        self.model = model
        self.uninstall = uninstall
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            if self.uninstall:
                self.log.emit(f"Removing {self.model.env.path}")
                success = self.model.uninstall_dependencies()
                message = "" if success else (
                    "Some files could not be removed. Close other programs using them and try again.")
            else:
                success = self.model.install_dependencies(self.log.emit, self.cancel_event)
                message = self.model.last_error
        except ProcessCancelled:
            self.done.emit(False, "Cancelled")
        except Exception as e:
            traceback.print_exc()
            self.done.emit(False, str(e) or type(e).__name__)
        else:
            self.done.emit(success, message)


class BatchWorker(QThread):
    """
    Separates a queue of audio files one after another.

    Args:
        jobs: List of (job id, path of the audio file)
        model: The separation model to use
        model_label: Model name shown to the user
        session_dir: Directory for the working files
        two_stems: Whether to separate into just vocals and instrumental
        options: Processing options (see Settings.processing_options)
        export: None, or (destination directory, format, bitrate) to save
                the stems of every file automatically. Without a destination
                directory the stems are saved next to their source file.
    """

    job_started = pyqtSignal(int)
    job_progress = pyqtSignal(int, int)
    job_status = pyqtSignal(int, str)
    # job id, SeparationResult, folder the stems were saved to ("" if not saved),
    # reason the stems could not be saved ("" if there was no problem)
    job_finished = pyqtSignal(int, object, str, str)
    job_failed = pyqtSignal(int, str)
    # True if the batch was cancelled
    batch_finished = pyqtSignal(bool)

    def __init__(self, jobs, model, model_label, session_dir, two_stems=False, options=None,
                 export=None, parent=None):
        super().__init__(parent)
        self.jobs = list(jobs)
        self.model = model
        self.model_label = model_label
        self.session_dir = session_dir
        self.two_stems = two_stems
        self.options = options or {}
        self.export = export
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        cancelled = False
        try:
            cancelled = self.run_jobs()
        finally:
            # Always reported, so the window can never stay stuck in "processing"
            self.batch_finished.emit(cancelled or self.cancel_event.is_set())

    def run_jobs(self):
        """Process the queue. Returns True if it was cancelled."""
        folders = pipeline.ExportFolders()
        for job_id, path in self.jobs:
            if self.cancel_event.is_set():
                return True
            self.job_started.emit(job_id)
            try:
                result = pipeline.separate_file(
                    self.model, path, self.session_dir,
                    two_stems=self.two_stems,
                    options=self.options,
                    progress=lambda value, job_id=job_id: self.job_progress.emit(job_id, value),
                    status=lambda text, job_id=job_id: self.job_status.emit(job_id, text),
                    cancel_event=self.cancel_event,
                    model_label=self.model_label,
                )
            except ProcessCancelled:
                return True
            except Exception as e:
                traceback.print_exc()
                self.job_failed.emit(job_id, str(e) or type(e).__name__)
                continue

            # A failed save must not throw away the separation itself
            saved_to, save_error = "", ""
            if self.export is not None:
                destination, fmt, bitrate = self.export
                self.job_status.emit(job_id, "Saving stems...")
                try:
                    saved_to = str(pipeline.export_result(
                        result, destination or os.path.dirname(path), fmt, bitrate,
                        cancel_event=self.cancel_event, folders=folders))
                except ProcessCancelled:
                    save_error = "Saving was cancelled"
                except Exception as e:
                    traceback.print_exc()
                    save_error = str(e) or type(e).__name__
            self.job_finished.emit(job_id, result, saved_to, save_error)
        return self.cancel_event.is_set()
