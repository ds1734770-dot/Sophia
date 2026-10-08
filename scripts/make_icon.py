"""
Builds assets/sophia.ico (used by the packaged exe) from the car drawing.

    python scripts/make_icon.py
"""

import io
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

from app.ui.main_window import ICON_SIZES, render_icon


def main():

    app = QApplication([])

    images = []

    for size in ICON_SIZES:

        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)

        render_icon(size).save(buffer, "PNG")

        images.append(Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA"))

    largest = images[-1]

    out = os.path.join("assets", "sophia.ico")

    largest.save(out, format="ICO", sizes=[(s, s) for s in ICON_SIZES], append_images=images[:-1])

    print(f"Wrote {out}")

    return app


if __name__ == "__main__":
    main()
