"""
What you see while Sophia works your screen: a soft amber border around
the display and a pill saying what she is doing (mouse clicks pass
straight through), ripples where she clicks, and a Stop chip. Stopping is
also possible with the global hotkey or by throwing the mouse into a
screen corner.
"""

import sys
import math
import time

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QPushButton, QWidget

AMBER = QColor("#ffb800")
RIPPLE_SECONDS = 0.7
MAX_RIPPLES = 12
BORDER = 5


def primary_geometry():

    screen = QGuiApplication.primaryScreen()

    return screen.geometry() if screen is not None else QRect(0, 0, 1280, 720)


class ControlOverlay(QWidget):
    """
    Click-through: it draws on top of everything but never receives the mouse.
    """

    def __init__(self, hotkey_label="Ctrl+Alt+X"):

        super().__init__(
            None,
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.WindowTransparentForInput,
        )

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.hotkey_label = hotkey_label
        self.goal = ""
        self.ripples = []

        self._clock = time.monotonic
        self._started = self._clock()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)

    # ------------------------------------------------

    def start(self, goal):

        self.goal = goal
        self._started = self._clock()

        self.setGeometry(primary_geometry())

        self.show()
        self.raise_()

        self._timer.start(33)

    def finish(self):

        self._timer.stop()
        self.ripples.clear()
        self.hide()

    def ripple(self, x, y):
        """
        Show where Sophia just clicked (screen coordinates).
        """

        local = self.mapFromGlobal(QPointF(x, y).toPoint())

        self.ripples.append((QPointF(local), self._clock()))

        del self.ripples[:-MAX_RIPPLES]

    # ------------------------------------------------

    def paintEvent(self, event):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        now = self._clock()

        pulse = 0.5 + 0.5 * math.sin((now - self._started) * 3.0)

        # glowing frame around the screen
        for i, width in enumerate((BORDER * 3, BORDER * 2, BORDER)):

            color = QColor(AMBER)
            color.setAlpha(int((18 + 12 * pulse) * (i + 1)))

            painter.setPen(QPen(color, width))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(self.rect()).adjusted(width / 2, width / 2, -width / 2, -width / 2))

        # the status pill, top centre
        text = f"Sophia is working: {self.goal[:70]}   ·   Stop: {self.hotkey_label}"

        font = QFont("Helvetica Neue" if sys.platform == "darwin" else "Segoe UI", 10)
        font.setBold(True)

        painter.setFont(font)

        width = painter.fontMetrics().horizontalAdvance(text) + 36

        pill = QRectF((self.width() - width) / 2, 12, width, 34)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(16, 19, 26, 235))
        painter.drawRoundedRect(pill, 17, 17)

        painter.setPen(QPen(AMBER, 1.4))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(pill, 17, 17)

        # a live dot
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 184, 0, int(120 + 135 * pulse)))
        painter.drawEllipse(QPointF(pill.left() + 17, pill.center().y()), 4.5, 4.5)

        painter.setPen(QColor("#f3f4f8"))
        painter.drawText(pill.adjusted(30, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, text)

        # where she clicked
        alive = []

        for point, born in self.ripples:

            age = (now - born) / RIPPLE_SECONDS

            if age >= 1:
                continue

            alive.append((point, born))

            ring = QColor(AMBER)
            ring.setAlpha(int(230 * (1 - age)))

            painter.setPen(QPen(ring, 3 * (1 - age) + 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(point, 8 + 40 * age, 8 + 40 * age)

        self.ripples = alive

        painter.end()


class StopChip(QPushButton):
    """
    A small, always clickable Stop button under the pill.
    """

    stop_requested = Signal()

    def __init__(self):

        super().__init__(
            "■  Stop",
            None,
        )

        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
        )

        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(96, 32)

        self.setStyleSheet(
            "QPushButton { background: #ff6b6b; color: white; border: none; border-radius: 16px;"
            " font-weight: 700; font-size: 13px; }"
            "QPushButton:hover { background: #ff8585; }"
        )

        self.clicked.connect(self.stop_requested)

    def place(self):

        area = primary_geometry()

        self.move(area.center().x() - self.width() // 2, area.top() + 54)

    def appear(self):

        self.place()
        self.show()
        self.raise_()
