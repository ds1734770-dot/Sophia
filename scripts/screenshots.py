"""
Render README images of Sophia's interface off-screen (no display or API
key needed):

    QT_QPA_PLATFORM=offscreen python scripts/screenshots.py

Writes docs/images/car.png and docs/images/chat.png.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SOPHIA_HOME", tempfile.mkdtemp(prefix="sophia-shots-"))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

OUT = ROOT / "docs" / "images"

app = QApplication.instance() or QApplication([])

from app.ui import theme  # noqa: E402

app.setStyleSheet(theme.STYLE)


def settle(seconds=1.5):

    end = time.time() + seconds

    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def on_background(widget, path, background="#14161c", pad=24):
    """
    The widget's pixels on a solid background (it is see-through),
    cropped to what is drawn.
    """

    from PySide6.QtCore import QRect

    pixmap = widget.grab()
    source = pixmap.toImage()

    xs, ys = [], []

    for y in range(0, source.height(), 2):
        for x in range(0, source.width(), 2):
            if source.pixelColor(x, y).alpha() > 8:
                xs.append(x)
                ys.append(y)

    if xs:
        pixmap = pixmap.copy(QRect(min(xs), min(ys), max(xs) - min(xs) + 2, max(ys) - min(ys) + 2))

    image = QImage(pixmap.width() + pad * 2, pixmap.height() + pad * 2, QImage.Format_ARGB32)
    image.fill(QColor(background))

    painter = QPainter(image)
    painter.drawPixmap(pad, pad, pixmap)
    painter.end()

    image.save(str(path))
    print("wrote", path.relative_to(ROOT))


def car_images():

    from app.ui.floating_car import FloatingCar

    for character, name in (("car", "car.png"),):

        settings = QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat)

        car = FloatingCar(settings=settings, width=260)
        car.set_character(character)
        car.show()

        settle(2.0)

        on_background(car, OUT / name)

        car.close()


class Pending:
    def needs_confirmation(self):
        return False


class FakeSophia:
    """
    Enough of Sophia for the chat window to show a conversation.
    """

    def __init__(self):
        from types import SimpleNamespace

        self.memory = SimpleNamespace(get_history=lambda: [
            {"role": "user", "content": "Hey Sophia, open YouTube and play some lofi"},
            {"role": "assistant", "content": "Playing lofi on YouTube."},
            {"role": "user", "content": "What's using the most memory?"},
            {"role": "assistant", "content": "Google Chrome is using 2.1 GB, then Visual Studio Code with 1.3 GB. "
                                             "Your Mac has 9.4 GB free."},
        ])
        self.pending_actions = SimpleNamespace(current=lambda: Pending())

    def start_services(self):
        pass

    def respond(self, text, on_text=None):
        return {"response": "", "tool_used": False}


def chat_image():

    from app.ui.main_window import MainWindow

    class Autostart:
        def is_enabled(self):
            return False

        def set_enabled(self, value):
            pass

    sophia = FakeSophia()

    window = MainWindow(
        lambda: sophia,
        settings=QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat),
        use_tray=False,
        autostart=Autostart(),
    )

    window.resize(560, 640)
    window.show()

    settle(2.5)

    window.grab().save(str(OUT / "chat.png"))
    print("wrote", (OUT / "chat.png").relative_to(ROOT))

    window.close()


if __name__ == "__main__":

    OUT.mkdir(parents=True, exist_ok=True)

    car_images()
    chat_image()
