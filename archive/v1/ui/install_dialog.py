from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QProgressBar
)
from PyQt6.QtGui import QFontDatabase

from ui.workers import InstallWorker


class InstallDialog(QDialog):
    """
    Installs or uninstalls the backend of a model, showing the installer
    output while it runs.
    """

    def __init__(self, parent, model, title, uninstall=False):
        """
        Args:
            parent: Parent widget
            model: Model whose backend is installed or removed
            title: Name of the backend shown to the user
            uninstall: Remove the backend instead of installing it
        """
        super().__init__(parent)
        self.model = model
        self.title = title
        self.uninstall = uninstall
        self.success = False
        self.running = True

        self.setWindowTitle(("Uninstalling " if uninstall else "Installing ") + title)
        self.setMinimumSize(680, 420)
        self.init_ui()

        self.worker = InstallWorker(model, uninstall, self)
        self.worker.log.connect(self.append_log)
        self.worker.done.connect(self.on_done)
        self.worker.start()

    def init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)

        if self.uninstall:
            text = f"Removing {self.title} and its downloaded model weights..."
        else:
            text = (f"Installing {self.title} into its own environment. "
                    "This downloads several large packages and can take a few minutes.")
        self.message_label = QLabel(text)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        # Indeterminate progress while working
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # Installer output
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.log_view, 1)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel)
        # Deleting files cannot be interrupted halfway
        self.cancel_button.setVisible(not self.uninstall)
        button_layout.addWidget(self.cancel_button)
        self.close_button = QPushButton("Close")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)

    def append_log(self, line):
        self.log_view.appendPlainText(line)

    def cancel(self):
        if self.running:
            self.cancel_button.setEnabled(False)
            self.message_label.setText("Cancelling...")
            self.worker.cancel()

    def on_done(self, success, message):
        self.running = False
        self.success = success
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1 if success else 0)
        self.cancel_button.setVisible(False)
        self.close_button.setEnabled(True)
        self.close_button.setDefault(True)

        action = "uninstalled" if self.uninstall else "installed"
        if success:
            self.message_label.setText(f"{self.title} was {action} successfully.")
        elif message == "Cancelled":
            self.message_label.setText("The installation was cancelled.")
        else:
            self.message_label.setText(f"<b>{self.title} could not be {action}.</b>")
            # The installer usually reported the reason in the log already
            if message and message not in self.log_view.toPlainText():
                self.append_log("")
                self.append_log(message)

    def reject(self):
        """Closing the window while working cancels the installation."""
        if self.running:
            if not self.uninstall:
                self.cancel()
            return
        super().reject()

    def done(self, result):
        self.worker.wait()
        super().done(result)

    @classmethod
    def run(cls, parent, model, title, uninstall=False):
        """
        Show the dialog and wait until it is closed.

        Returns:
            bool: True if the operation succeeded
        """
        dialog = cls(parent, model, title, uninstall)
        dialog.exec()
        return dialog.success
