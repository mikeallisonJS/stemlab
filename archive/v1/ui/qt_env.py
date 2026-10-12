"""Environment tweaks that have to happen before Qt is started."""

import os


def quiet_multimedia_logging():
    """
    Keep Qt's audio backend from printing the details of every file it plays.

    FFmpeg writes those straight to the console. With QT_FFMPEG_DEBUG set, Qt
    routes FFmpeg's messages through its own logging instead, where the debug
    and info levels can be switched off. Warnings and errors are still shown.
    """
    if "QT_FFMPEG_DEBUG" in os.environ:
        # Someone asked for the full output
        return
    os.environ["QT_FFMPEG_DEBUG"] = "1"
    rules = os.environ.get("QT_LOGGING_RULES", "")
    quiet = "default.debug=false;default.info=false"
    os.environ["QT_LOGGING_RULES"] = f"{quiet};{rules}" if rules else quiet
