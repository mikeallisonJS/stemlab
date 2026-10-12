"""Application-wide light and dark themes."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

ACCENT = "#2a82da"

# Styling shared by both themes; colors come from the active palette
STYLESHEET = """
QToolTip {
    color: palette(tool-tip-text);
    background-color: palette(tool-tip-base);
    border: 1px solid palette(mid);
}
QPushButton {
    padding: 5px 14px;
}
QProgressBar {
    text-align: center;
    min-height: 18px;
}
QTreeWidget, QListWidget, QPlainTextEdit, QTextBrowser {
    border: 1px solid palette(mid);
}
"""


def dark_palette() -> QPalette:
    palette = QPalette()
    window = QColor("#1e1e1e")
    base = QColor("#252526")
    button = QColor("#2d2d30")
    text = QColor("#e0e0e0")
    disabled = QColor("#6e6e6e")

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, button)
    palette.setColor(QPalette.ColorRole.ToolTipBase, button)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.PlaceholderText, disabled)
    palette.setColor(QPalette.ColorRole.Button, button)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#62aaff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Light, QColor("#4a4a4f"))
    palette.setColor(QPalette.ColorRole.Midlight, QColor("#3e3e42"))
    palette.setColor(QPalette.ColorRole.Mid, QColor("#3e3e42"))
    palette.setColor(QPalette.ColorRole.Dark, QColor("#151515"))
    palette.setColor(QPalette.ColorRole.Shadow, QColor("#000000"))

    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#3e3e42"))
    return palette


def light_palette() -> QPalette:
    # Spelled out rather than taken from the style: its standard palette
    # follows the operating system and is dark on a dark system
    palette = QPalette()
    window = QColor("#f0f0f0")
    text = QColor("#1e1e1e")
    disabled = QColor("#a0a0a0")

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#e9e9e9"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffdc"))
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.PlaceholderText, disabled)
    palette.setColor(QPalette.ColorRole.Button, QColor("#e6e6e6"))
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#0a58ca"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Light, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Midlight, QColor("#e3e3e3"))
    palette.setColor(QPalette.ColorRole.Mid, QColor("#b4b4b4"))
    palette.setColor(QPalette.ColorRole.Dark, QColor("#a0a0a0"))
    palette.setColor(QPalette.ColorRole.Shadow, QColor("#696969"))

    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#c8c8c8"))
    return palette


def system_prefers_dark(app: QApplication) -> bool:
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        # Qt older than 6.5 cannot tell
        return False


def _set_color_scheme(app: QApplication, scheme) -> None:
    try:
        app.styleHints().setColorScheme(scheme)
    except AttributeError:
        # Added in Qt 6.8
        pass


def apply_theme(app: QApplication, theme: str = "system") -> bool:
    """
    Apply a theme to the whole application.

    Args:
        app: The application instance
        theme: "dark", "light" or "system" (follow the operating system)

    Returns:
        True if the dark theme is now active
    """
    if theme not in ("dark", "light"):
        # Stop overriding the system's choice before asking for it
        _set_color_scheme(app, Qt.ColorScheme.Unknown)
    dark = theme == "dark" or (theme not in ("dark", "light") and system_prefers_dark(app))
    # Lets the parts Qt does not draw itself (the title bar) follow the theme
    _set_color_scheme(app, Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    app.setStyle("Fusion")
    app.setPalette(dark_palette() if dark else light_palette())
    app.setStyleSheet(STYLESHEET)
    return dark
