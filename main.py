#!/usr/bin/env python3
import sys
import os
import traceback

# Run from any working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.qt_env import quiet_multimedia_logging
quiet_multimedia_logging()

from PyQt6.QtWidgets import QApplication, QMessageBox
from core.settings import Settings
from ui.main_window import MainWindow
from ui.styles.dark_mode import apply_theme

def show_unexpected_error(exc_type, exc_value, exc_traceback):
    """
    Report errors nobody handled. Without this hook PyQt terminates the
    application when an exception escapes an event handler.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    sys.stderr.write(details)
    if QApplication.instance() is not None:
        box = QMessageBox(QMessageBox.Icon.Critical, "Unexpected Error",
                          f"An unexpected error occurred:\n{exc_value or exc_type.__name__}")
        box.setDetailedText(details)
        box.exec()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CaptainStems")
    app.setOrganizationName("CaptainStems")
    sys.excepthook = show_unexpected_error

    settings = Settings()
    apply_theme(app, settings.theme())

    window = MainWindow(settings)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
