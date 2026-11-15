"""The main window: connects the rows, the settings and the audio engine."""

import ctypes
import re
import threading

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from ..devices import BUILTIN, EXTERNAL, classify, list_devices
from ..engine import Engine
from .icon import app_icon
from .tokens import build_palette, build_qss, theme
from .tray import TrayIcon
from .widgets import SEMIBOLD, DeviceRow, ElidedLabel, LinkButton, SourceRow, make_font

THEME_CHOICES = [("Auto", "auto"), ("Dark", "dark"), ("Light", "light")]


class DeviceMonitor(QThread):
    """Polls the device list off the UI thread and reports only real changes."""

    changed = Signal(list)

    def __init__(self, list_fn, interval: float = 3.0):
        super().__init__()
        self._list = list_fn
        self._interval = interval
        self._stop = threading.Event()

    def run(self):
        last = None
        while not self._stop.is_set():
            try:
                devs = self._list()
            except Exception:  # noqa: BLE001
                devs = None
            if devs is not None:
                key = (tuple(sorted(d.id for d in devs)), next((d.id for d in devs if d.is_default), None))
                if key != last:
                    last = key
                    self.changed.emit(devs)
            self._stop.wait(self._interval)

    def stop(self):
        self._stop.set()
        self.wait(3000)


def set_native_titlebar(widget: QWidget) -> None:
    """Make Windows' own title bar follow the theme (dark mode, caption and text colours)."""
    try:
        dwm = ctypes.windll.dwmapi
        hwnd = int(widget.winId())
        t = theme.t

        def put(attr: int, value: int) -> None:
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)

        def colorref(hexs: str) -> int:
            c = QColor(hexs)
            return (c.blue() << 16) | (c.green() << 8) | c.red()

        put(20, 1 if t["dark"] else 0)      # immersive dark mode (Windows 11 / 10 2004+)
        put(19, 1 if t["dark"] else 0)      # older Windows 10 builds
        put(35, colorref(t["bar"]))         # caption colour (Windows 11)
        put(36, colorref(t["text"]))        # caption text colour (Windows 11)
    except Exception:  # noqa: BLE001 - cosmetic only
        pass


class MainWindow(QWidget):
    engineEvent = Signal(str, dict)

    def __init__(self, settings, list_fn=list_devices, engine_factory=Engine, monitor_interval: float = 3.0,
                 use_tray: bool = True):
        super().__init__()
        self.setObjectName("root")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setWindowTitle("Audio Splitter")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(380)
        self.resize(440, 520)

        self.settings = settings
        self.tray = None                   # created below, once the window exists
        self._quitting = False
        self.devices = []
        self.source_id = ""
        self.sharing = False
        self.source_lost = False
        self.lost: set = set()
        self.known_ids: dict = {}          # device name -> last seen id (so lost devices can be retried)
        self.rows: dict = {}               # device name -> DeviceRow

        self.engine = engine_factory(lambda kind, **d: self.engineEvent.emit(kind, d))
        self.engineEvent.connect(self.on_engine_event)

        # ── layout ──
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 16, 16, 8)
        bl.setSpacing(0)
        heading = QLabel("Sound")
        heading.setObjectName("heading")
        heading.setFont(make_font(13, SEMIBOLD))
        bl.addWidget(heading)
        bl.addSpacing(6)

        self.tree = QWidget()
        self.tree_l = QVBoxLayout(self.tree)
        self.tree_l.setContentsMargins(0, 0, 0, 0)
        self.tree_l.setSpacing(0)
        self.src_row = SourceRow()
        self.src_row.sourceChanged.connect(self.on_source_picked)
        self.tree_l.addWidget(self.src_row)
        bl.addWidget(self.tree)

        self.empty = self._build_empty()
        bl.addWidget(self.empty)
        bl.addSpacing(14)

        opt = QHBoxLayout()
        opt.setContentsMargins(0, 0, 0, 8)
        theme_lbl = QLabel("Theme")
        theme_lbl.setObjectName("hint")
        theme_lbl.setFont(make_font(13))
        self.theme_combo = QComboBox()
        self.theme_combo.setAccessibleName("Theme")
        for label, key in THEME_CHOICES:
            self.theme_combo.addItem(label, key)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(settings.theme)))
        self.theme_combo.currentIndexChanged.connect(self.on_theme_picked)
        opt.addWidget(theme_lbl)
        opt.addStretch(1)
        opt.addWidget(self.theme_combo)
        bl.addLayout(opt)
        outer.addWidget(body)
        outer.addStretch(1)

        footer = QFrame()
        footer.setObjectName("footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 12, 16, 12)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.RichText)
        self.status.setFont(make_font(14))
        self.status.setAccessibleName("Status")
        self.go = QPushButton("Start sharing")
        self.go.setFont(make_font(14, SEMIBOLD))
        self.go.clicked.connect(self.toggle_sharing)
        fl.addWidget(self.status, 1)
        fl.addWidget(self.go)
        outer.addWidget(footer)

        # ── level meter timer: runs only while sharing ──
        self.level_timer = QTimer(self)
        self.level_timer.setInterval(33)
        self.level_timer.timeout.connect(self.update_levels)
        self._smooth: dict = {}

        # ── theme ──
        theme.changed.connect(self.apply_theme)
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _s: self._follow_system())
        self._follow_system(first=True)

        # ── system tray: the app keeps running there when its window is closed ──
        if use_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = TrayIcon(self)
            self.tray.showRequested.connect(self.show_window)
            self.tray.windowToggled.connect(self.toggle_window)
            self.tray.toggleRequested.connect(self.toggle_sharing)
            self.tray.quitRequested.connect(self.quit_app)
            self.tray.show()

        # ── devices ──
        self.monitor = DeviceMonitor(list_fn, monitor_interval)
        self.monitor.changed.connect(self.on_devices)
        self.monitor.start()

    # ── building blocks ───────────────────────────────────────────
    def _build_empty(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 20, 4, 12)
        lay.setSpacing(8)
        title = QLabel("No other audio devices found.")
        title.setFont(make_font(14, SEMIBOLD))
        hint = QLabel("Pair headphones or a speaker in Windows, turn them on, and they will show up here by themselves.")
        hint.setObjectName("hint")
        hint.setFont(make_font(13))
        hint.setWordWrap(True)
        link = LinkButton("Open Bluetooth settings")
        link.setProperty("emphasis", True)
        link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("ms-settings:bluetooth")))
        lay.addWidget(title)
        lay.addWidget(hint)
        lay.addWidget(link, 0, Qt.AlignmentFlag.AlignLeft)
        w.setVisible(False)
        return w

    def _make_row(self, name: str) -> DeviceRow:
        row = DeviceRow(name)
        row.toggled.connect(lambda on, n=name: self.on_toggled(n, on))
        row.delayChanged.connect(lambda ms, n=name: self.on_delay(n, ms))
        return row

    # ── theme ─────────────────────────────────────────────────────
    def _follow_system(self, first: bool = False) -> None:
        choice = self.settings.theme
        if choice == "auto":
            dark = QGuiApplication.styleHints().colorScheme() != Qt.ColorScheme.Light
            name = "dark" if dark else "light"
        else:
            name = choice
        if first and theme.name == name:
            self.apply_theme()
        else:
            theme.set(name)

    def on_theme_picked(self, _index: int) -> None:
        self.settings.theme = self.theme_combo.currentData()
        self.settings.save()
        self._follow_system()

    def apply_theme(self) -> None:
        t = theme.t
        QApplication.instance().setPalette(build_palette(t))
        self.setStyleSheet(build_qss(t))
        self.src_row.update()
        self.setWindowIcon(app_icon(style=theme.name))
        QApplication.instance().setWindowIcon(app_icon(style=theme.name))
        for row in self.rows.values():
            row.apply_theme()
        self.refresh(snap=True)
        set_native_titlebar(self)

    def showEvent(self, event):
        super().showEvent(event)
        set_native_titlebar(self)
        QTimer.singleShot(0, self.setFocus)      # start with no control focused, like a fresh window

    # ── device list ───────────────────────────────────────────────
    def on_devices(self, devs) -> None:
        old_source = self.source_id
        self.devices = list(devs)
        ids = {d.id for d in self.devices}
        if self.source_id not in ids:
            default = next((d for d in self.devices if d.is_default), None)
            self.source_id = default.id if default else (self.devices[0].id if self.devices else "")
        for d in self.devices:
            self.known_ids[d.name] = d.id
        self.rebuild_rows()
        if self.sharing:
            if self.source_id != old_source:
                self._restart_sharing()
            else:
                self.engine.set_targets(self._targets())
        self.refresh()

    def on_source_picked(self, device_id: str) -> None:
        if not device_id or device_id == self.source_id:
            return
        self.source_id = device_id
        self.rebuild_rows()
        if self.sharing:
            self._restart_sharing()
        self.refresh()

    def rebuild_rows(self) -> None:
        source = next((d for d in self.devices if d.id == self.source_id), None)
        active = [d for d in self.devices if d.kind == EXTERNAL and d.id != self.source_id]
        active_names = [d.name for d in active]
        for d in active:
            if d.name not in self.settings.devices:
                self.settings.device(d.name)
                self.settings.save()
        remembered = [n for n in self.settings.devices
                      if n not in active_names and classify(n) == EXTERNAL and (not source or n != source.name)]
        order = active_names + remembered

        changed = False
        for name in list(self.rows):
            if name not in order:
                row = self.rows.pop(name)
                self.tree_l.removeWidget(row)
                row.deleteLater()
                changed = True
        for name in order:
            if name not in self.rows:
                self.rows[name] = self._make_row(name)
                self.tree_l.addWidget(self.rows[name])
                changed = True
        current = [self.tree_l.itemAt(i).widget() for i in range(1, self.tree_l.count())]
        wanted = [self.rows[n] for n in order]
        if changed or current != wanted:
            for row in current:
                self.tree_l.removeWidget(row)
            for row in wanted:
                self.tree_l.addWidget(row)
        self.src_row.set_devices(self.devices, self.source_id)

    # ── actions ───────────────────────────────────────────────────
    def _targets(self) -> dict:
        """What the engine should play to, read from settings (the source of truth), not from the rows."""
        present = {d.name for d in self.devices}
        out = {}
        for name in self.rows:
            st = self.settings.device(name)
            if st["enabled"] and (name in present or name in self.lost) and name in self.known_ids:
                out[self.known_ids[name]] = st["delay"]
        return out

    def toggle_sharing(self) -> None:
        if self.sharing:
            self.engine.stop()
            self.sharing = False
            self.lost.clear()
            self.source_lost = False
            self.level_timer.stop()
        else:
            targets = self._targets()
            if not targets or not self.source_id:
                return
            self.engine.start(self.source_id, targets)
            self.sharing = True
            self.level_timer.start()
        self.refresh()

    def _restart_sharing(self) -> None:
        self.engine.stop()
        targets = self._targets()
        if targets and self.source_id:
            self.engine.start(self.source_id, targets)
        else:
            self.sharing = False
            self.level_timer.stop()

    def on_toggled(self, name: str, enabled: bool) -> None:
        self.settings.device(name)["enabled"] = enabled
        self.settings.save()
        if not enabled:
            self.lost.discard(name)
        if self.sharing:
            self.engine.set_targets(self._targets())
        self.refresh()

    def on_delay(self, name: str, ms: int) -> None:
        self.settings.device(name)["delay"] = ms
        self.settings.save()
        if self.sharing and name in self.known_ids:
            self.engine.set_delay(self.known_ids[name], ms)

    def on_engine_event(self, kind: str, data: dict) -> None:
        by_id = {v: k for k, v in self.known_ids.items()}
        name = by_id.get(data.get("id", ""))
        if kind == "target_lost" and name:
            self.lost.add(name)
        elif kind == "target_ready" and name:
            self.lost.discard(name)
        elif kind == "source_lost":
            self.source_lost = True
        elif kind == "source_ready":
            self.source_lost = False
        self.refresh()

    def update_levels(self) -> None:
        levels = self.engine.levels()
        for name, row in self.rows.items():
            if not row.is_on:
                continue
            raw = levels.get(self.known_ids.get(name, ""), 0.0)
            cur = self._smooth.get(name, 0.0)
            cur = raw if raw > cur else cur * 0.85 + raw * 0.15     # fast attack, slow release
            self._smooth[name] = cur
            row.level.set_value(cur)

    # ── refresh everything in place ───────────────────────────────
    def refresh(self, snap: bool = False) -> None:
        order = [self.tree_l.itemAt(i).widget() for i in range(1, self.tree_l.count())]
        present_names = {d.name for d in self.devices}
        for row in order:
            name = row.name
            st = self.settings.device(name)
            present = name in present_names
            lost = self.sharing and st["enabled"] and name in self.lost
            if lost:
                sub = "Lost connection. Retrying…"
            elif present:
                sub = "Connected"
            else:
                sub = "Not connected. Turn it on and it will join."
            row.apply_state(present=present, enabled=st["enabled"], lost=lost, delay=st["delay"], sub_text=sub)
        self._refresh_source()
        self._refresh_trunk(order, snap)
        has_rows = bool(order)
        self.empty.setVisible(not has_rows)
        self._refresh_footer(order)
        self.layout().activate()
        self.resize(self.width(), self.sizeHint().height())

    def _refresh_source(self) -> None:
        src = next((d for d in self.devices if d.id == self.source_id), None)
        if self.source_lost and self.sharing:
            self.src_row.set_sub("Lost the source. Retrying…", True)
        elif src is None:
            self.src_row.set_sub("No output device found.", True)
        elif not src.is_default:
            self.src_row.set_sub("Windows is not playing sound here. Make it the default output.", True)
        elif src.kind == BUILTIN:
            self.src_row.set_sub("Source. Laptop speakers play too. Make a headphone the default.")
        else:
            self.src_row.set_sub("Source. Plays directly, laptop speakers stay silent.")

    def _refresh_trunk(self, order, snap: bool) -> None:
        t = theme
        flow = self.sharing
        on = [r.is_on for r in order]

        def lit(flag: bool) -> QColor:
            return t.color("accent") if (flow and flag) else t.color("rail")

        self.src_row.last = not order
        self.src_row.set_rail(down=lit(any(on)), dot_filled=flow, snap=snap)
        for k, row in enumerate(order):
            row.first = False
            row.last = k == len(order) - 1
            after = any(on[k + 1:])
            row.set_rail(up=lit(on[k] or after), down=lit(after), elbow=lit(on[k]),
                         dashed=flow and row.lost, snap=snap)

    def _refresh_footer(self, order) -> None:
        n_on = sum(1 for r in order if r.is_on)
        n_lost = sum(1 for r in order if r.lost)
        if not order:
            text = "Nothing to share to yet"
        elif self.sharing:
            text = f"<b>Sharing to {n_on}</b>" + (f" · {n_lost} reconnecting" if n_lost else "")
        elif n_on:
            text = f"Ready · {n_on} device{'s' if n_on != 1 else ''} selected"
        else:
            text = "Pick at least one device"
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {theme.t['text'] if self.sharing else theme.t['muted']};")
        if self.tray is not None:
            self.tray.set_state(self.sharing, re.sub(r"<[^>]+>", "", text), n_on > 0)
        self.go.setText("Stop" if self.sharing else "Start sharing")
        self.go.setObjectName("secondary" if self.sharing else "primary")
        self.go.setEnabled(self.sharing or n_on > 0)
        self.go.style().unpolish(self.go)
        self.go.style().polish(self.go)

    # ── window and tray ───────────────────────────────────────────
    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_window(self) -> None:
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            self.show_window()

    def quit_app(self) -> None:
        self._quitting = True
        self.close()
        QApplication.quit()

    def closeEvent(self, event):
        if self.tray is not None and not self._quitting:      # the X button hides to the tray
            event.ignore()
            self.hide()
            self.tray.notify_once()
            return
        self.level_timer.stop()
        self.engine.stop()
        self.monitor.stop()
        if self.tray is not None:
            self.tray.hide()
        super().closeEvent(event)
