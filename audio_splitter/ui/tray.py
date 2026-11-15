"""System tray icon: shows state at a glance, and lets the app keep running with its window closed."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .icon import app_icon
from .tokens import theme


class TrayIcon(QSystemTrayIcon):
    showRequested = Signal()
    windowToggled = Signal()
    toggleRequested = Signal()
    quitRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(app_icon(active=False, style=theme.name), parent)
        self._notified = False
        self._menu = QMenu()
        self.act_show = self._menu.addAction("Show Audio Splitter")
        self.act_go = self._menu.addAction("Start sharing")
        self._menu.addSeparator()
        self.act_quit = self._menu.addAction("Quit")
        self.act_show.triggered.connect(self.showRequested)
        self.act_go.triggered.connect(self.toggleRequested)
        self.act_quit.triggered.connect(self.quitRequested)
        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)
        self.setToolTip("Audio Splitter")

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:      # a plain left click
            self.windowToggled.emit()

    def set_state(self, sharing: bool, text: str, can_start: bool) -> None:
        """Lit icon while sharing, dim while idle (the rail lighting up, in miniature)."""
        self.setIcon(app_icon(active=sharing, style=theme.name))
        self.setToolTip(f"Audio Splitter\n{text}")
        self.act_go.setText("Stop sharing" if sharing else "Start sharing")
        self.act_go.setEnabled(sharing or can_start)

    def notify_once(self) -> None:
        """Tell the user, one time, that closing the window did not quit the app."""
        if not self._notified and self.supportsMessages():
            self._notified = True
            self.showMessage("Audio Splitter is still running",
                             "It lives in the tray. Right-click the icon to quit.",
                             QSystemTrayIcon.MessageIcon.NoIcon, 4000)
