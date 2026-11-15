"""Run the window:  python -m fernwire.ui

Developer options:
  --demo                     fake devices, no hardware needed
  --theme auto|dark|light
  --state idle|sharing|lost|empty|tune   (needs --demo)
  --screenshot FILE.png      save a picture of the window and quit
"""

import argparse
import ctypes
import sys
from functools import partial

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ..settings import Settings
from .demo import FakeEngine, MemorySettings, demo_devices
from .icon import app_icon
from .tokens import theme
from .widgets import make_font
from .window import MainWindow


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fernwire.ui")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--theme", choices=["auto", "dark", "light"])
    ap.add_argument("--state", choices=["idle", "sharing", "lost", "empty", "tune"], default="idle")
    ap.add_argument("--screenshot")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    try:    # own taskbar identity, so Windows shows OUR icon (not python.exe's) and groups it correctly
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Fernwire.App")
    except Exception:  # noqa: BLE001
        pass
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setFont(make_font(14))
    app.setApplicationName("Fernwire")

    if args.demo:
        empty = args.state == "empty"
        settings = MemorySettings(empty=empty)
        win = MainWindow(settings, list_fn=partial(demo_devices, empty), engine_factory=FakeEngine,
                         monitor_interval=60, use_tray=False)
    else:
        settings = Settings()
        win = MainWindow(settings)
    if args.theme:                       # this run only: never written to the settings file
        win.theme_combo.blockSignals(True)
        win.theme_combo.setCurrentIndex(max(0, win.theme_combo.findData(args.theme)))
        win.theme_combo.blockSignals(False)
        settings.theme = args.theme
        win._follow_system()
    app.setQuitOnLastWindowClosed(win.tray is None)      # with a tray, closing the window keeps the app running
    win.show()

    if args.demo:
        QTimer.singleShot(250, lambda: _apply_state(win, args.state))
    if args.screenshot:
        QTimer.singleShot(1300, lambda: _shoot(app, win, args.screenshot))
    return app.exec()


def _apply_state(win: MainWindow, state: str) -> None:
    if state in ("sharing", "lost", "tune"):
        win.toggle_sharing()
    if state == "lost":
        win.lost.add("SoundPeats T3 Pro")
        win.refresh()
    if state == "tune":
        row = win.rows.get("SoundPeats T3 Pro")
        if row:
            row.toggle_panel()
            win.refresh()


def _shoot(app: QApplication, win: MainWindow, path: str) -> None:
    win.grab().save(path)       # only the window's own pixels; never the screen
    win.quit_app()


if __name__ == "__main__":
    raise SystemExit(main())
