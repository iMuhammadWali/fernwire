"""Design tokens for the two themes. These mirror design/mockup.html: change them in both places."""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette

THEMES = {
    # dark:. True neutral greys (equal R/G/B), silver = active.
    "dark": {
        "stage": "#080808", "win": "#181818", "bar": "#222222",
        "line": "#2e2e2e", "divider": "#262626", "rail": "#666666", "line_strong": "#707070",
        "track": "#2b2b2b", "faint": "#8a8a8a",
        "text": "#f2f2f2", "muted": "#ababab",
        "accent": "#e6e6e6", "accent_ink": "#0c0c0c", "accent_weak": "#2e2e2e",
        "error": "#d9745b", "off": "#707070", "knob": "#ececec",
        "origin": "#e6e6e6", "origin_idle": "#ababab",
        "tune_bg": "#202020", "tune_line": "#3a3a3a",
        "dark": True,
    },
    # light: white ground, one blue accent.
    "light": {
        "stage": "#dfe6f0", "win": "#ffffff", "bar": "#f3f6fb",
        "line": "#dde4ee", "divider": "#e9eef5", "rail": "#8693a6", "line_strong": "#7f8b9d",
        "track": "#e6ebf2", "faint": "#6b7789",
        "text": "#15202e", "muted": "#566478",
        "accent": "#1c5fd1", "accent_ink": "#ffffff", "accent_weak": "#dbe7fb",
        "error": "#c62828", "off": "#7f8b9d", "knob": "#ffffff",
        "origin": "#1c5fd1", "origin_idle": "#566478",
        "tune_bg": "#f3f6fb", "tune_line": "#dde4ee",
        "dark": False,
    },
}


class ThemeManager(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.name = "dark"
        self.t = THEMES["dark"]

    def set(self, name: str) -> None:
        if name not in THEMES:
            return
        self.name = name
        self.t = THEMES[name]
        self.changed.emit()

    def color(self, key: str) -> QColor:
        return QColor(self.t[key])


theme = ThemeManager()


def build_palette(t: dict) -> QPalette:
    """Palette so native pieces (combo popup, tooltips, scrollbars) follow the theme."""
    p = QPalette()
    c = QColor
    for role, key in [
        (QPalette.Window, "win"), (QPalette.WindowText, "text"), (QPalette.Base, "bar"),
        (QPalette.AlternateBase, "win"), (QPalette.Text, "text"), (QPalette.Button, "bar"),
        (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "bar"), (QPalette.ToolTipText, "text"),
        (QPalette.Highlight, "accent_weak"), (QPalette.HighlightedText, "text"),
        (QPalette.PlaceholderText, "muted"), (QPalette.Link, "accent"),
    ]:
        p.setColor(role, c(t[key]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, c(t["faint"]))
    return p


def build_qss(t: dict) -> str:
    return f"""
    QWidget#root {{ background: {t['win']}; }}
    QLabel {{ color: {t['text']}; background: transparent; }}
    QLabel#heading {{ color: {t['muted']}; }}
    QLabel#hint {{ color: {t['muted']}; }}
    QFrame#footer {{ background: {t['bar']}; border: 0; border-top: 1px solid {t['line']}; }}
    QFrame#panel {{ background: {t['tune_bg']}; border: 1px solid {t['tune_line']}; border-radius: 6px; }}

    QComboBox {{ background: {t['bar']}; color: {t['text']}; border: 1px solid {t['line_strong']};
                 border-radius: 6px; padding: 5px 8px; }}
    QComboBox:focus {{ border: 2px solid {t['accent']}; padding: 4px 7px; }}
    QComboBox::drop-down {{ border: 0; width: 24px; }}
    QComboBox QAbstractItemView {{ background: {t['bar']}; color: {t['text']}; border: 1px solid {t['line_strong']};
                 selection-background-color: {t['accent_weak']}; selection-color: {t['text']}; outline: 0; }}

    QPushButton {{ font-weight: 600; border-radius: 6px; padding: 7px 18px; }}
    QPushButton#primary {{ background: {t['accent']}; color: {t['accent_ink']}; border: 1px solid transparent; }}
    QPushButton#primary:hover {{ background: {t['accent']}; border: 1px solid {t['text']}; }}
    QPushButton#primary:disabled {{ background: {t['off']}; color: {t['win']}; }}
    QPushButton#primary:focus {{ border: 2px solid {t['text']}; padding: 6px 17px; }}
    QPushButton#secondary {{ background: transparent; color: {t['text']}; border: 1px solid {t['line_strong']}; }}
    QPushButton#secondary:hover {{ background: {t['accent_weak']}; }}
    QPushButton#secondary:focus {{ border: 2px solid {t['text']}; padding: 6px 17px; }}
    QPushButton#link {{ background: transparent; border: 0; padding: 0; font-weight: 400;
                 text-align: left; text-decoration: underline; color: {t['muted']}; }}
    QPushButton#link[emphasis="true"] {{ color: {t['text']}; font-weight: 600; }}
    QPushButton#link:hover {{ color: {t['text']}; }}
    QPushButton#link:focus {{ color: {t['text']}; }}

    QSlider::groove:horizontal {{ height: 4px; background: {t['track']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {t['accent']}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
    QSlider::handle:horizontal:focus {{ border: 2px solid {t['text']}; width: 10px; height: 10px; margin: -5px 0; }}
    """
