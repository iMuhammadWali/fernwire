"""Write audio_splitter/assets/icon.ico + icon_light.ico (and .png) from the code-drawn icon.

    python tools/make_icon.py
"""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from audio_splitter.ui.icon import draw_icon  # noqa: E402

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def png_bytes(image) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path: Path, style: str) -> None:
    pngs = [(s, png_bytes(draw_icon(s, True, style))) for s in ICO_SIZES]
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    directory, body = b"", b""
    for size, data in pngs:
        directory += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        body += data
        offset += len(data)
    path.write_bytes(header + directory + body)


if __name__ == "__main__":
    app = QGuiApplication([])
    out = Path(__file__).resolve().parent.parent / "audio_splitter" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    for style, suffix in (("dark", ""), ("light", "_light")):
        write_ico(out / f"icon{suffix}.ico", style)
        draw_icon(256, True, style).save(str(out / f"icon{suffix}.png"))
        print("wrote", out / f"icon{suffix}.ico", "and", out / f"icon{suffix}.png")
