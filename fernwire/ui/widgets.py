"""Custom widgets: switch, level bar, elided label, link button and the rail rows."""

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QSlider, QVBoxLayout, QWidget)

from .tokens import theme

SEMIBOLD = QFont.Weight.DemiBold
NORMAL = QFont.Weight.Normal


def make_font(px: int, weight=NORMAL) -> QFont:
    f = QFont("Segoe UI")
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def mix(a: QColor, b: QColor, k: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * k), int(a.green() + (b.green() - a.green()) * k),
                  int(a.blue() + (b.blue() - a.blue()) * k))


# ── labels and buttons ────────────────────────────────────────────
class ElidedLabel(QLabel):
    """A single-line label that ends in an ellipsis instead of growing the row."""

    def __init__(self, text="", px=13, weight=NORMAL):
        super().__init__(text)
        self._color = QColor("#ffffff")
        self.setFont(make_font(px, weight))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    def set_weight(self, weight) -> None:
        f = self.font()
        f.setWeight(weight)
        self.setFont(f)
        self.update()

    def minimumSizeHint(self):
        s = super().minimumSizeHint()
        s.setWidth(0)
        return s

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(self._color)
        text = QFontMetrics(self.font()).elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width())
        p.drawText(self.rect(), int(self.alignment()), text)


class LinkButton(QPushButton):
    """Underlined inline link. Its width always reserves the bold width, so emphasis never resizes it."""

    def __init__(self, text=""):
        super().__init__(text)
        self.setObjectName("link")
        self.setFont(make_font(13))
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setProperty("emphasis", False)
        self.setText(text)

    def setText(self, text: str) -> None:
        super().setText(text)
        bold = QFontMetrics(make_font(13, SEMIBOLD))
        self.setFixedSize(bold.horizontalAdvance(text) + 4, 25)   # 25px tall hit area, laid out as 19

    def set_emphasis(self, on: bool) -> None:
        self.setProperty("emphasis", on)
        self.style().unpolish(self)
        self.style().polish(self)


class Switch(QAbstractButton):
    """On/off switch. The focus ring only shows for keyboard focus, like Windows."""

    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(50, 29)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pos = 0.0
        self._ring = False
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self._animate)
        theme.changed.connect(self.update)

    def set_checked_silent(self, on: bool) -> None:
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def _set_pos(self, v) -> None:
        self._pos = float(v)
        self.update()

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def focusInEvent(self, e):
        self._ring = e.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason,
                                    Qt.FocusReason.ShortcutFocusReason)
        super().focusInEvent(e)
        self.update()

    def focusOutEvent(self, e):
        self._ring = False
        super().focusOutEvent(e)
        self.update()

    def paintEvent(self, _event):
        t = theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.45)
        track = QRectF(3, 4.5, 44, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(t.color("off"), t.color("accent"), self._pos))
        p.drawRoundedRect(track, 10, 10)
        p.setBrush(mix(t.color("knob"), t.color("accent_ink"), self._pos))
        x = 3 + 3 + 24 * self._pos
        p.drawEllipse(QRectF(x, 7.5, 14, 14))
        if self._ring and self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(t.color("accent"), 2))
            p.drawRoundedRect(track.adjusted(-2, -2, 2, 2), 12, 12)


class LevelBar(QWidget):
    """Thin level meter. It always takes its space, so showing it never changes a row's height."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(3)
        self._value = 0.0
        self._active = False

    def set_active(self, on: bool) -> None:
        if on != self._active:
            self._active = on
            self.update()

    def set_value(self, v: float) -> None:
        v = max(0.0, min(1.0, v))
        if abs(v - self._value) > 0.004:
            self._value = v
            self.update()

    def paintEvent(self, _event):
        if not self._active:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        r = QRectF(self.rect())
        p.setBrush(theme.color("track"))
        p.drawRoundedRect(r, 1.5, 1.5)
        if self._value > 0:
            p.setBrush(theme.color("accent"))
            p.drawRoundedRect(QRectF(0, 0, r.width() * self._value, r.height()), 1.5, 1.5)


# ── rail rows ─────────────────────────────────────────────────────
class RailRow(QWidget):
    """A row of the tree. It paints its own slice of the shared trunk, its branch, and its divider.

    The trunk is lit from the source down to the last ACTIVE device and passes straight by any
    device that is off or lost, so the path never looks broken. ``up`` colours the half above the
    branch, ``down`` the half below.
    """

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind            # "src" or "dev"
        self.first = False
        self.last = False
        self.dashed = False         # lost device: branch drawn dashed in the error colour
        self.dot_filled = False
        self._cols = {k: QColor(theme.t["rail"]) for k in ("up", "down", "elbow")}
        self._anims = {}
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_rail(self, up=None, down=None, elbow=None, dashed=None, dot_filled=None, snap=False) -> None:
        if dashed is not None:
            self.dashed = dashed
        if dot_filled is not None:
            self.dot_filled = dot_filled
        for key, target in (("up", up), ("down", down), ("elbow", elbow)):
            if target is not None:
                self._fade(key, QColor(target), snap)
        self.update()

    def _fade(self, key: str, target: QColor, snap: bool) -> None:
        cur = self._cols[key]
        anim = self._anims.get(key)
        if anim is not None:
            anim.stop()
        if snap or cur == target:
            self._cols[key] = target
            return
        anim = QVariantAnimation(self)
        anim.setDuration(200)
        anim.setStartValue(cur)
        anim.setEndValue(target)
        anim.valueChanged.connect(lambda c, k=key: self._set_col(k, c))
        self._anims[key] = anim
        anim.start()

    def _set_col(self, key: str, color) -> None:
        self._cols[key] = QColor(color)
        self.update()

    def paintEvent(self, _event):
        t = theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        if not self.first:
            p.fillRect(0, 0, w, 1, t.color("divider"))
        x = 13
        if self.kind == "src":
            if not self.last:
                p.fillRect(x, 26, 2, h - 26, self._cols["down"])
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            ring = t.color("origin") if self.dot_filled else t.color("origin_idle")
            p.setPen(QPen(ring, 2))
            p.setBrush(ring if self.dot_filled else t.color("win"))
            p.drawEllipse(QRectF(8, 21, 12, 12))
        else:
            if not self.last:
                p.fillRect(x, 27, 2, h - 27, self._cols["down"])
            p.fillRect(x, 1, 2, 26, self._cols["up"])
            if self.dashed:
                p.setPen(Qt.PenStyle.NoPen)
                for dx in range(0, 18, 7):
                    p.fillRect(x + dx, 27, min(4, 18 - dx), 2, t.color("error"))
            else:
                p.fillRect(x, 27, 18, 2, self._cols["elbow"])


class SourceRow(RailRow):
    sourceChanged = Signal(str)

    def __init__(self):
        super().__init__("src")
        self.first = True
        self.setFixedHeight(71)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 10, 0, 10)
        lay.setSpacing(0)
        self.combo = QComboBox()
        self.combo.setFixedHeight(32)
        self.combo.setAccessibleName("Sound source")
        self.combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.combo.currentIndexChanged.connect(lambda _i: self.sourceChanged.emit(self.combo.currentData() or ""))
        self.sub = ElidedLabel()
        self.sub.setFixedHeight(19)
        lay.addWidget(self.combo)
        lay.addWidget(self.sub)

    def set_devices(self, devices, source_id: str) -> None:
        """Fill the picker in place, keeping the current choice."""
        self.combo.blockSignals(True)
        self.combo.clear()
        for d in devices:
            self.combo.addItem(d.name + (" (Windows default)" if d.is_default else ""), d.id)
        idx = self.combo.findData(source_id)
        self.combo.setCurrentIndex(max(0, idx))
        self.combo.blockSignals(False)

    def set_sub(self, text: str, error: bool = False) -> None:
        self.sub.setText(text)
        self.sub.setToolTip(text)
        self.sub.set_color(theme.color("error" if error else "muted"))


class DeviceRow(RailRow):
    toggled = Signal(bool)
    delayChanged = Signal(int)

    def __init__(self, name: str):
        super().__init__("dev")
        self.name = name
        self.present = False
        self.enabled = True
        self.lost = False
        self.delay = 0
        self.panel_open = False

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 11, 0, 10)     # 1px divider + 10px padding
        root.setSpacing(0)

        line1 = QWidget()
        line1.setFixedHeight(29)
        l1 = QHBoxLayout(line1)
        l1.setContentsMargins(0, 0, -3, 0)
        l1.setSpacing(12)
        self.name_lbl = ElidedLabel(name, 15, SEMIBOLD)
        self.name_lbl.setFixedHeight(22)
        self.switch = Switch()
        self.switch.setAccessibleName(f"Play on {name}")
        self.switch.toggled.connect(self.toggled)
        l1.addWidget(self.name_lbl, 1)
        l1.addWidget(self.switch)
        root.addWidget(line1)

        subw = QWidget()
        subw.setFixedHeight(25)
        sl = QHBoxLayout(subw)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        self.sub = ElidedLabel()
        self.sep = ElidedLabel(" · ")
        self.sep.setFixedWidth(self.sep.fontMetrics().horizontalAdvance(" · ") + 2)
        self.link = LinkButton("No delay")
        self.link.setAccessibleName(f"Delay for {name}")
        self.link.clicked.connect(self.toggle_panel)
        sl.addWidget(self.sub)
        sl.addWidget(self.sep)
        sl.addWidget(self.link)
        sl.addStretch(1)
        root.addWidget(subw)

        root.addSpacing(3)
        self.level = LevelBar()
        root.addWidget(self.level)
        root.addSpacing(2)

        self.panel_wrap = QWidget()
        pw = QVBoxLayout(self.panel_wrap)
        pw.setContentsMargins(0, 8, 0, 0)
        panel = QFrame()
        panel.setObjectName("panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(12, 10, 12, 10)
        pl.setSpacing(6)
        ctl = QHBoxLayout()
        ctl.setSpacing(12)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 80)               # steps of 5 ms, 0 to 400 ms
        self.slider.setAccessibleName(f"Delay for {name}")
        self.slider.valueChanged.connect(self._slider_changed)
        self.value_lbl = ElidedLabel("0 ms")
        self.value_lbl.setFixedWidth(56)
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ctl.addWidget(self.slider, 1)
        ctl.addWidget(self.value_lbl)
        pl.addLayout(ctl)
        self.hint = QLabel("Delay this device if it plays ahead of the others.")
        self.hint.setObjectName("hint")
        self.hint.setFont(make_font(13))
        self.hint.setWordWrap(True)
        pl.addWidget(self.hint)
        pw.addWidget(panel)
        self.panel_wrap.setVisible(False)
        root.addWidget(self.panel_wrap)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.apply_theme()

    # ── state ─────────────────────────────────────────────────────
    @property
    def is_on(self) -> bool:
        return self.present and self.enabled and not self.lost

    def toggle_panel(self) -> None:
        self.panel_open = not self.panel_open
        self._sync_panel()

    def _slider_changed(self, v: int) -> None:
        ms = v * 5
        self.delay = ms
        self.value_lbl.setText(f"{ms} ms")
        self._sync_link()
        self.delayChanged.emit(ms)

    def _sync_link(self) -> None:
        text = f"+{self.delay} ms delay" if self.delay else "No delay"
        self.link.setText(text)
        self.link.set_emphasis(self.delay > 0)

    def _sync_panel(self) -> None:
        self.panel_wrap.setVisible(self.panel_open and self.is_on)
        self.updateGeometry()

    def apply_state(self, *, present: bool, enabled: bool, lost: bool, delay: int, sub_text: str) -> None:
        """Update every widget in place (never recreated, so keyboard focus stays put)."""
        self.present, self.enabled, self.lost, self.delay = present, enabled, lost, delay
        on = self.is_on
        self.name_lbl.set_weight(SEMIBOLD if on else NORMAL)
        self.switch.setEnabled(present or lost)
        self.switch.set_checked_silent(enabled)
        self.sub.setText(sub_text)
        self.sub.setToolTip(sub_text)
        self.switch.setAccessibleDescription(sub_text)
        self.slider.blockSignals(True)
        self.slider.setValue(delay // 5)
        self.slider.blockSignals(False)
        self.value_lbl.setText(f"{delay} ms")
        self._sync_link()
        self.link.setVisible(on)
        self.sep.setVisible(on)
        self.level.set_active(on)
        if not on:
            self.level.set_value(0)
            self.panel_open = False
        self._sync_panel()
        self.apply_theme()

    def apply_theme(self) -> None:
        t = theme
        self.name_lbl.set_color(t.color("text") if self.is_on else t.color("muted"))
        if self.lost:
            self.sub.set_color(t.color("error"))
        elif not self.present:
            self.sub.set_color(t.color("faint"))
        else:
            self.sub.set_color(t.color("muted"))
        self.sep.set_color(t.color("muted"))
        self.value_lbl.set_color(t.color("text"))
        self.update()
