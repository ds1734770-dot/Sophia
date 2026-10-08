"""
The floating orb: Sophia's always-on-top avatar that you can put anywhere
on the screen.

    1 click   listen (voice request)
    2 clicks  move mode: the orb follows the pointer, click once to drop it
    3 clicks  open the full chat, docked beside the orb
    right-click for a menu

Answers appear in a small speech bubble beside the orb (and are spoken).
"""

import logging

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSettings,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QCursor, QGuiApplication, QPainter, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.orb import OrbWidget

log = logging.getLogger("sophia.ui")

ORB_SIZE = 130
EDGE_MARGIN = 8
GESTURE_MS = 350
MOVE_TICK_MS = 8

BUBBLE_MAX_WIDTH = 360
BUBBLE_SECONDS_MIN = 4.0
BUBBLE_CHARS_PER_SECOND = 14.0


# ---------------------------------------------------------------
# Click counting
# ---------------------------------------------------------------

class GestureDetector(QObject):
    """
    Turns rapid clicks into one gesture: after the clicks stop for
    `interval_ms`, emits the count (1, 2 or 3; more counts as 3).
    """

    gesture = Signal(int)

    def __init__(self, interval_ms=GESTURE_MS, parent=None):

        super().__init__(parent)

        self.interval_ms = interval_ms

        self._count = 0

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._flush)

    def register_click(self):

        self._count += 1

        # a third click is final: no need to wait any longer
        if self._count >= 3:

            self._flush()

            return

        self._timer.start(self.interval_ms)

    def _flush(self):

        self._timer.stop()

        count, self._count = min(self._count, 3), 0

        if count:
            self.gesture.emit(count)

    def cancel(self):

        self._timer.stop()
        self._count = 0


# ---------------------------------------------------------------
# Screen helpers
# ---------------------------------------------------------------

def screen_rects():
    """
    The usable area of every monitor.
    """

    return [s.availableGeometry() for s in QGuiApplication.screens()]


def clamp_to_screens(top_left, size, rects=None):
    """
    Keep a window of `size` fully on some monitor, nearest to where it
    was put. Returns the corrected top-left QPoint.
    """

    rects = rects or screen_rects()

    if not rects:
        return top_left

    center = QPoint(top_left.x() + size.width() // 2, top_left.y() + size.height() // 2)

    def distance(rect):

        dx = max(rect.left() - center.x(), 0, center.x() - rect.right())
        dy = max(rect.top() - center.y(), 0, center.y() - rect.bottom())

        return dx * dx + dy * dy

    rect = min(rects, key=distance)

    x = max(rect.left() + EDGE_MARGIN, min(top_left.x(), rect.right() - size.width() - EDGE_MARGIN))
    y = max(rect.top() + EDGE_MARGIN, min(top_left.y(), rect.bottom() - size.height() - EDGE_MARGIN))

    return QPoint(x, y)


def default_position(size):
    """
    Bottom-right of the primary monitor.
    """

    screen = QGuiApplication.primaryScreen()

    area = screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)

    return QPoint(
        area.right() - size.width() - 40,
        area.bottom() - size.height() - 60,
    )


# ---------------------------------------------------------------
# Speech bubble
# ---------------------------------------------------------------

class SpeechBubble(QWidget):
    """
    A small answer bubble next to the orb. It fades away by itself,
    unless it asks a question (Yes / No buttons stay until answered).
    """

    answered = Signal(str)
    clicked = Signal()

    def __init__(self):

        super().__init__(
            None,
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.MarkdownText)
        self.label.setMaximumWidth(BUBBLE_MAX_WIDTH)
        self.label.setStyleSheet(f"color: {theme.TEXT}; font-size: 14px; background: transparent;")

        layout.addWidget(self.label)

        self.buttons = QWidget()
        row = QHBoxLayout(self.buttons)
        row.setContentsMargins(0, 0, 0, 0)

        self._always = QPushButton("Always allow")
        self._always.clicked.connect(lambda: self._answer("always"))

        yes = QPushButton("Yes")
        yes.setObjectName("yes")
        yes.clicked.connect(lambda: self._answer("yes"))

        no = QPushButton("No")
        no.setObjectName("no")
        no.clicked.connect(lambda: self._answer("no"))

        row.addWidget(yes)
        row.addWidget(self._always)
        row.addWidget(no)
        row.addStretch()

        layout.addWidget(self.buttons)

        self.buttons.hide()

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.fade_out)

        self._fade = None

    # ------------------------------------------------

    def show_message(self, text, anchor, confirm=False, allow_always=False):
        """
        Show `text` beside the `anchor` rectangle (the orb, in screen
        coordinates).
        """

        self._hide_timer.stop()

        if self._fade is not None:
            self._fade.stop()

        self.label.setText(text)

        self.buttons.setVisible(confirm)
        self._always.setVisible(allow_always)

        self.adjustSize()

        self.place_beside(anchor)

        self.setWindowOpacity(0.0)
        self.show()

        self._animate(0.0, 1.0, 180)

        if not confirm:

            seconds = max(BUBBLE_SECONDS_MIN, len(text) / BUBBLE_CHARS_PER_SECOND)

            self._hide_timer.start(int(seconds * 1000))

    def place_beside(self, anchor):

        rects = screen_rects()

        area = min(
            rects,
            key=lambda r: (r.center() - anchor.center()).manhattanLength(),
        ) if rects else QRect(0, 0, 1280, 720)

        size = self.sizeHint()

        gap = 10

        # toward the middle of the screen
        if anchor.center().x() > area.center().x():
            x = anchor.left() - size.width() - gap

        else:
            x = anchor.right() + gap

        y = anchor.center().y() - size.height() // 2

        self.move(clamp_to_screens(QPoint(x, y), size, rects))

    def fade_out(self):

        if self.isVisible():

            self._animate(self.windowOpacity(), 0.0, 350, then=self.hide)

    def dismiss(self):

        self._hide_timer.stop()

        if self._fade is not None:
            self._fade.stop()

        self.hide()

    def _animate(self, start, end, ms, then=None):

        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(ms)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.OutCubic)

        if then is not None:
            animation.finished.connect(then)

        animation.start()

        self._fade = animation

    def _answer(self, answer):

        self.dismiss()

        self.answered.emit(answer)

    # ------------------------------------------------

    def mouseReleaseEvent(self, event):

        self.clicked.emit()

    def paintEvent(self, event):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(QColor(theme.BORDER))
        painter.setBrush(QColor(theme.PANEL))

        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)

        painter.end()


# ---------------------------------------------------------------
# The orb window
# ---------------------------------------------------------------

class FloatingOrb(QWidget):

    listen_requested = Signal()
    chat_requested = Signal()
    quit_requested = Signal()
    toggle_voice_replies = Signal(bool)
    toggle_hands_free = Signal(bool)

    def __init__(self, model, settings=None, gesture_ms=GESTURE_MS, cursor=QCursor.pos):

        super().__init__(
            None,
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.model = model
        self.settings = settings or QSettings("Sophia", "Sophia")
        self._cursor = cursor

        self.setFixedSize(ORB_SIZE, ORB_SIZE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.orb = OrbWidget(model, ORB_SIZE)
        self.orb.setToolTip(
            "1 click: talk   2 clicks: move   3 clicks: open chat   right-click: menu"
        )
        self.orb.clicked.connect(self._on_click)

        layout.addWidget(self.orb)

        self.gestures = GestureDetector(gesture_ms, self)
        self.gestures.gesture.connect(self._on_gesture)

        self.moving = False

        self._move_timer = QTimer(self)
        self._move_timer.timeout.connect(self._follow_cursor)

        self.bubble = SpeechBubble()
        self.bubble.clicked.connect(self.chat_requested)

        self.voice_replies_action = None
        self.hands_free_action = None

        self.restore_position()

    # ------------------------------------------------
    # Position
    # ------------------------------------------------

    def restore_position(self):

        saved = self.settings.value("orb_pos")

        try:

            point = QPoint(int(saved[0]), int(saved[1])) if saved else default_position(self.size())

        except (TypeError, ValueError, IndexError):

            point = default_position(self.size())

        self.move(clamp_to_screens(point, self.size()))

    def save_position(self):

        self.settings.setValue("orb_pos", [self.x(), self.y()])

    def reset_position(self):

        self.move(clamp_to_screens(default_position(self.size()), self.size()))

        self.save_position()

    # ------------------------------------------------
    # Gestures
    # ------------------------------------------------

    def _on_click(self):

        # while moving, any click drops the orb
        if self.moving:

            self.drop()

            return

        self.bubble.dismiss()

        self.gestures.register_click()

    def _on_gesture(self, count):

        if count == 1:
            self.listen_requested.emit()

        elif count == 2:
            self.start_move_mode()

        else:
            self.chat_requested.emit()

    # ------------------------------------------------
    # Move mode
    # ------------------------------------------------

    def start_move_mode(self):

        self.moving = True
        self.model.moving = True

        self.bubble.dismiss()

        self._move_timer.start(MOVE_TICK_MS)

        self._follow_cursor()

    def _follow_cursor(self):

        pos = self._cursor()

        target = QPoint(pos.x() - self.width() // 2, pos.y() - self.height() // 2)

        self.move(clamp_to_screens(target, self.size()))

    def drop(self):

        self._move_timer.stop()

        self.moving = False
        self.model.moving = False

        self.save_position()

    # ------------------------------------------------
    # Answers
    # ------------------------------------------------

    def say(self, text, confirm=False, allow_always=False):
        """
        Show a reply in the bubble beside the orb.
        """

        if self.moving:
            return

        self.bubble.show_message(text, self.frameGeometry(), confirm, allow_always)

    # ------------------------------------------------
    # Menu
    # ------------------------------------------------

    def contextMenuEvent(self, event):

        self.gestures.cancel()

        menu = QMenu(self)

        chat = menu.addAction("Open chat")
        chat.triggered.connect(self.chat_requested)

        talk = menu.addAction("Talk")
        talk.triggered.connect(self.listen_requested)

        menu.addSeparator()

        if self.voice_replies_action is not None:
            menu.addAction(self.voice_replies_action)

        if self.hands_free_action is not None:
            menu.addAction(self.hands_free_action)

        move = menu.addAction("Move orb")
        move.triggered.connect(self.start_move_mode)

        reset = menu.addAction("Reset position")
        reset.triggered.connect(self.reset_position)

        menu.addSeparator()

        quit_action = menu.addAction("Quit Sophia")
        quit_action.triggered.connect(self.quit_requested)

        menu.exec(event.globalPos())

    def closeEvent(self, event):

        self.bubble.close()

        super().closeEvent(event)


def dock_beside(window, orb_rect):
    """
    Put the chat window next to the orb (on the side with more room),
    kept on screen.
    """

    rects = screen_rects()

    if not rects:
        return

    area = min(rects, key=lambda r: (r.center() - orb_rect.center()).manhattanLength())

    size = window.size()

    gap = 14

    if orb_rect.center().x() > area.center().x():
        x = orb_rect.left() - size.width() - gap

    else:
        x = orb_rect.right() + gap

    y = orb_rect.center().y() - size.height() // 2

    window.move(clamp_to_screens(QPoint(x, y), size, rects))


class OrbController(QObject):
    """
    Connects the floating orb to the chat window (which holds Sophia).
    """

    def __init__(self, window, orb):

        super().__init__()

        self.window = window
        self.orb = orb

        window.extra_orbs.append(orb.orb)
        window.hide_on_close = True

        orb.listen_requested.connect(self.listen)
        orb.chat_requested.connect(self.open_chat)
        orb.quit_requested.connect(window.quit)

        orb.bubble.answered.connect(self._answer)

        window.replied.connect(self._on_reply)
        window.hint.connect(self._on_hint)

        orb.voice_replies_action = window.voice_toggle_action()
        orb.hands_free_action = window.hands_free_action

    # ------------------------------------------------

    def listen(self):

        self.window.start_voice_turn()

    def open_chat(self):

        self.orb.bubble.dismiss()

        dock_beside(self.window, self.orb.frameGeometry())

        self.window.bring_to_front()

    def _answer(self, answer):

        self.window.send(answer)

    def _on_reply(self, text, confirm, allow_always):

        # with the chat open, the reply is already there
        if self.window.isVisible():
            return

        self.orb.say(text, confirm, allow_always)

    def _on_hint(self, text):

        if not self.window.isVisible():
            self.orb.say(text)

    def hotkey(self):

        self.listen()
