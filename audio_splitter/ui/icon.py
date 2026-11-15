"""The app icon, drawn in code so it is crisp at every size and needs no image files at runtime.

A source dot with a wire hanging from it and two leaves growing alternately along it, right then left:
one source feeding several outputs, in a living shape. Dark theme: silver on a near-black tile. Light
theme: blue on a white tile.
The tray version is dim while idle and lit while sharing, like the rail in the window.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)

# One look per app theme, so the icon belongs to whichever theme is active.
PALETTES = {
    "dark": {"tile": "#181818", "edge": "#3a3a3a", "lit": "#e6e6e6", "dim": "#8a8a8a"},
    "light": {"tile": "#ffffff", "edge": "#b9c6d8", "lit": "#1c5fd1", "dim": "#7f8b9d"},
}


def _leaf(base: QPointF, tip: QPointF, width: float) -> QPainterPath:
    """A pointed leaf between two points: two gentle curves bulging to either side."""
    mid = QPointF((base.x() + tip.x()) / 2, (base.y() + tip.y()) / 2)
    dx, dy = tip.x() - base.x(), tip.y() - base.y()
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    nx, ny = -dy / length, dx / length                       # unit normal to the leaf's axis
    c1 = QPointF(mid.x() + nx * width, mid.y() + ny * width)
    c2 = QPointF(mid.x() - nx * width, mid.y() - ny * width)
    path = QPainterPath(base)
    path.quadTo(c1, tip)
    path.quadTo(c2, base)
    return path


def draw_icon(size: int, active: bool = True, style: str = "dark") -> QImage:
    pal = PALETTES.get(style, PALETTES["dark"])
    tile_c, edge_c = QColor(pal["tile"]), QColor(pal["edge"])
    color = QColor(pal["lit"] if active else pal["dim"])

    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)

    edge = max(1.0, s / 48)
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(edge / 2, edge / 2, s - edge, s - edge), s * 0.22, s * 0.22)
    p.fillPath(tile, tile_c)
    p.setPen(QPen(edge_c, edge))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(tile)

    def pt(x: float, y: float) -> QPointF:
        return QPointF(x * s, y * s)

    # the wire: it hangs from the source dot and curves gently as it falls
    start = pt(0.43, 0.21)
    wire = QPainterPath(start)
    wire.cubicTo(pt(0.43, 0.46), pt(0.53, 0.54), pt(0.50, 0.85))
    w = max(1.8, s * 0.07)
    p.setPen(QPen(color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawPath(wire)

    # two leaves, alternating: one to the right, then one to the left, a little further down
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    for t, dx, dy, width in ((0.44, 0.30, -0.14, 0.14), (0.72, -0.29, -0.13, 0.14)):
        base = wire.pointAtPercent(t)
        tip = QPointF(base.x() + dx * s, base.y() + dy * s)
        p.drawPath(_leaf(base, tip, width * s))

    # the source: filled while sharing, hollow while idle (like the dot in the window)
    r = max(s * 0.095, w * 1.25)
    if active:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
    else:
        p.setPen(QPen(color, w))
        p.setBrush(tile_c)
    p.drawEllipse(QRectF(start.x() - r, start.y() - r, 2 * r, 2 * r))
    p.end()
    return img


def app_icon(active: bool = True, style: str = "dark") -> QIcon:
    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(QPixmap.fromImage(draw_icon(size, active, style)))
    return icon
