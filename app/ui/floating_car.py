"""
The floating car: Sophia's always-on-top character that sits anywhere on
the screen.

    drag            move it, like any other element
    hover           headlights on, engine revving, and three buttons
                    appear below it: Voice, Chat, Hide
    Alt+S           hide it (it drives off) or bring it back (it drives in)

Answers appear in a small text card above the car and are spoken.
"""

import logging

from PySide6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSettings,
    QTimer,
    QVariantAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.car import CANVAS_W, STATES, CarModel, draw_car

log = logging.getLogger("sophia.ui")

WIDTH = 300
HEIGHT = 236

# where the car is drawn inside the window
CAR_RECT = QRect(0, 22, WIDTH, 106)

# the part of the window that counts as "on the car"
CAR_HIT = QRect(26, 40, 248, 92)

BUTTON_SIZE = 42
BUTTON_GAP = 16
BUTTON_Y = 152
BUTTON_LABELS = ("Voice", "Chat", "Hide")

# logical canvas pixels per screen pixel
LOGICAL_PER_PIXEL = CANVAS_W / CAR_RECT.width()

FRAME_MS = 16
LEAVE_LINGER_MS = 650

ENTRY_MS = 1150
HIDE_MS = 700
REV_MS = 500
EXIT_MS = 850

CARD_MAX_WIDTH = 340
CARD_SECONDS_MIN = 4.0
CARD_CHARS_PER_SECOND = 14.0

YELLOW = "#ffc400"


# ---------------------------------------------------------------
# Screen helpers
# ---------------------------------------------------------------

def screen_rects():
    """
    The usable area of every monitor.
    """

    return [s.availableGeometry() for s in QGuiApplication.screens()]


def nearest_rect(point, rects=None):

    rects = rects or screen_rects()

    if not rects:
        return QRect(0, 0, 1280, 720)

    def distance(rect):

        dx = max(rect.left() - point.x(), 0, point.x() - rect.right())
        dy = max(rect.top() - point.y(), 0, point.y() - rect.bottom())

        return dx * dx + dy * dy

    return min(rects, key=distance)


def clamp_to_screens(top_left, size, rects=None, margin=0):
    """
    Keep a window of `size` fully on the monitor nearest to where it
    was put. Returns the corrected top-left QPoint.
    """

    rects = rects or screen_rects()

    if not rects:
        return top_left

    center = QPoint(top_left.x() + size.width() // 2, top_left.y() + size.height() // 2)

    rect = nearest_rect(center, rects)

    x = max(rect.left() + margin, min(top_left.x(), rect.right() - size.width() - margin))
    y = max(rect.top() + margin, min(top_left.y(), rect.bottom() - size.height() - margin))

    return QPoint(x, y)


def default_position(size):
    """
    Bottom-right of the primary monitor.
    """

    screen = QGuiApplication.primaryScreen()

    area = screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)

    return QPoint(area.right() - size.width() - 20, area.bottom() - size.height() - 10)


# ---------------------------------------------------------------
# Text card
# ---------------------------------------------------------------

class SpeechCard(QWidget):
    """
    A small rounded card with Sophia's answer, above the car. It fades
    away by itself, unless it asks a question (Yes / No stay until
    answered).
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
        self.label.setMaximumWidth(CARD_MAX_WIDTH)
        self.label.setStyleSheet(
            f"color: {theme.TEXT}; font-size: 14px; background: transparent;"
        )

        layout.addWidget(self.label)

        self.buttons = QWidget()
        row = QHBoxLayout(self.buttons)
        row.setContentsMargins(0, 0, 0, 0)

        yes = QPushButton("Yes")
        yes.setObjectName("yes")
        yes.clicked.connect(lambda: self._answer("yes"))

        self._always = QPushButton("Always allow")
        self._always.clicked.connect(lambda: self._answer("always"))

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
        Show `text` above the `anchor` rectangle (the car, in screen
        coordinates), or below it when there is no room above.
        """

        self._hide_timer.stop()

        if self._fade is not None:
            self._fade.stop()

        self.label.setText(text)

        self.buttons.setVisible(confirm)
        self._always.setVisible(allow_always)

        self.adjustSize()

        self.place_above(anchor)

        self.setWindowOpacity(0.0)
        self.show()

        self._animate(0.0, 1.0, 180)

        if not confirm:

            seconds = max(CARD_SECONDS_MIN, len(text) / CARD_CHARS_PER_SECOND)

            self._hide_timer.start(int(seconds * 1000))

    def place_above(self, anchor):

        rects = screen_rects()

        area = nearest_rect(anchor.center(), rects)

        size = self.sizeHint()

        gap = 6

        x = anchor.center().x() - size.width() // 2

        y = anchor.top() - size.height() - gap

        if y < area.top():
            y = anchor.bottom() + gap

        self.move(clamp_to_screens(QPoint(x, y), size, rects, margin=6))

    def fade_out(self):

        if self.isVisible():
            self._animate(self.windowOpacity(), 0.0, 350, then=self.hide)

    def dismiss(self):

        self._hide_timer.stop()

        if self._fade is not None:
            self._fade.stop()

        self.hide()

    def _animate(self, start, end, ms, then=None):

        from PySide6.QtCore import QPropertyAnimation

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
# Button icons
# ---------------------------------------------------------------

def _draw_icon(painter, kind, center, color):
    """
    Small line icons drawn in code: mic, chat and hide (a chevron).
    """

    pen = QPen(QColor(color), 2.2)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)

    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    cx, cy = center.x(), center.y()

    if kind == "Voice":

        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(cx - 4, cy - 10, 8, 14), 4, 4)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(QRectF(cx - 8, cy - 7, 16, 14), 200 * 16, 140 * 16)
        painter.drawLine(cx, cy + 7, cx, cy + 11)
        painter.drawLine(cx - 4, cy + 11, cx + 4, cy + 11)

    elif kind == "Chat":

        path = QPainterPath()
        path.addRoundedRect(QRectF(cx - 10, cy - 9, 20, 15), 5, 5)
        path.moveTo(cx - 4, cy + 6)
        path.lineTo(cx - 7, cy + 11)
        path.lineTo(cx + 1, cy + 6)

        painter.drawPath(path)

        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)

        for dx in (-5, 0, 5):
            painter.drawEllipse(QPoint(cx + dx, cy - 1), 1, 1)

    else:   # Hide

        painter.drawLine(cx - 7, cy - 3, cx, cy + 4)
        painter.drawLine(cx, cy + 4, cx + 7, cy - 3)
        painter.drawLine(cx - 8, cy + 9, cx + 8, cy + 9)


# ---------------------------------------------------------------
# The car window
# ---------------------------------------------------------------

class FloatingCar(QWidget):

    voice_requested = Signal()
    chat_requested = Signal()
    hide_requested = Signal()
    quit_requested = Signal()

    def __init__(self, settings=None, cursor=QCursor.pos):

        super().__init__(
            None,
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        self.settings = settings or QSettings("Sophia", "Sophia")
        self._cursor = cursor

        self.model = CarModel()

        self.setFixedSize(WIDTH, HEIGHT)

        self.card = SpeechCard()
        self.card.clicked.connect(self.chat_requested)

        # menu actions supplied by the controller
        self.voice_replies_action = None
        self.hands_free_action = None

        # hover and buttons
        self.interact = 0.0            # 0..1, how far the buttons are out
        self._inside = False
        self._leave_at = 0.0
        self._hovered_button = None
        self._pressed_button = None
        self.listening = False

        # dragging and driving
        self.dragging = False
        self._grab_offset = QPoint()
        self.driving = False
        self.hidden = False
        self._animation = None
        self._last_x = self.x()

        self.rest_pos = QPoint()
        self.restore_position()

        self._clock = QElapsedTimer()
        self._clock.start()
        self._now = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(FRAME_MS)

    # ------------------------------------------------
    # Position
    # ------------------------------------------------

    def restore_position(self):

        saved = self.settings.value("car_pos")

        try:

            point = QPoint(int(saved[0]), int(saved[1])) if saved else default_position(self.size())

        except (TypeError, ValueError, IndexError):

            point = default_position(self.size())

        self.rest_pos = clamp_to_screens(point, self.size())

        self.move(self.rest_pos)

        self._face_the_middle()

    def save_position(self):

        self.rest_pos = QPoint(self.x(), self.y())

        self.settings.setValue("car_pos", [self.x(), self.y()])

    def reset_position(self):

        self.rest_pos = clamp_to_screens(default_position(self.size()), self.size())

        self.move(self.rest_pos)

        self.save_position()

        self._face_the_middle()

    def _face_the_middle(self):
        """
        A parked car looks toward the middle of its screen.
        """

        area = nearest_rect(self.rest_pos + QPoint(WIDTH // 2, HEIGHT // 2))

        self.model.facing = -1 if self.rest_pos.x() + WIDTH // 2 > area.center().x() else 1

    # ------------------------------------------------
    # Driving animations
    # ------------------------------------------------

    def _drive(self, start, end, ms, curve, done=None):

        if self._animation is not None:
            self._animation.stop()

        animation = QVariantAnimation(self)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setDuration(ms)
        animation.setEasingCurve(curve)
        animation.valueChanged.connect(self.move)

        self.driving = True

        def finished():

            self.driving = False

            if done is not None:
                done()

        animation.finished.connect(finished)
        animation.start()

        self._animation = animation

        return animation

    def _edge_start(self, target):
        """
        Off-screen position on the nearer side edge, level with target.
        Also turns the car to face the way it will drive.
        """

        area = nearest_rect(target + QPoint(WIDTH // 2, HEIGHT // 2))

        from_left = target.x() + WIDTH // 2 < area.center().x()

        x = area.left() - WIDTH - 20 if from_left else area.right() + 20

        return QPoint(x, target.y()), from_left

    def enter(self):
        """
        Drive in from the nearest screen edge and park.
        """

        self.hidden = False

        start, from_left = self._edge_start(self.rest_pos)

        self.model.facing = 1 if from_left else -1

        self.move(start)
        self._last_x = start.x()

        self.show()

        def arrived():

            self.model.kick("honk")
            self.model.kick("bounce")

            self._face_the_middle()

        self._drive(start, self.rest_pos, ENTRY_MS, QEasingCurve.OutCubic, arrived)

    def hide_away(self):
        """
        Drive off the nearest edge and disappear.
        """

        if self.hidden or not self.isVisible():
            return

        self.hidden = True

        self.card.dismiss()

        target, from_left = self._edge_start(QPoint(self.x(), self.y()))

        # leave by the same side it would enter from
        self.model.facing = -1 if from_left else 1

        def gone():

            self.hide()

        self._drive(QPoint(self.x(), self.y()), target, HIDE_MS, QEasingCurve.InCubic, gone)

    def show_back(self):

        if self.hidden or not self.isVisible():
            self.enter()

    def toggle_visibility(self):

        if self.hidden or not self.isVisible():
            self.show_back()

        else:
            self.hide_away()

    def exit_and_quit(self, done):
        """
        Rev the engine, then speed off the right edge; `done` is called
        once the car has gone.
        """

        self.card.dismiss()

        self.dragging = False

        if self._animation is not None:
            self._animation.stop()

        self.model.facing = 1
        self.model.kick("honk")
        self.model.kick("shake")
        self.model.hover = True

        self.driving = True

        def go():

            area = nearest_rect(QPoint(self.x(), self.y()))

            self.model.hover = False

            self._drive(
                QPoint(self.x(), self.y()),
                QPoint(area.right() + 40, self.y()),
                EXIT_MS,
                QEasingCurve.InCubic,
                done,
            )

        QTimer.singleShot(REV_MS, go)

    # ------------------------------------------------
    # Per-frame update
    # ------------------------------------------------

    def set_activity(self, state, level):
        """
        What Sophia is doing (from the chat window): idle, listening,
        thinking, speaking or alert.
        """

        if state in STATES:

            self.model.set_state(state)
            self.model.set_level(level)

            self.listening = state == "listening"

    def _hover_zone(self):

        zone = QRect(CAR_HIT)

        if self.interact > 0.05:
            zone = zone.united(self._buttons_zone())

        return zone

    def _buttons_zone(self):

        total = 3 * BUTTON_SIZE + 2 * BUTTON_GAP

        return QRect((WIDTH - total) // 2 - 10, BUTTON_Y - 14, total + 20, BUTTON_SIZE + 34)

    def button_rect(self, index):

        total = 3 * BUTTON_SIZE + 2 * BUTTON_GAP

        x = (WIDTH - total) // 2 + index * (BUTTON_SIZE + BUTTON_GAP)

        return QRect(x, BUTTON_Y, BUTTON_SIZE, BUTTON_SIZE)

    def _tick(self):

        dt = self._clock.restart() / 1000

        self._now += dt

        # driving: tell the model how far we moved (in canvas pixels)
        dx = (self.x() - self._last_x) * LOGICAL_PER_PIXEL

        self._last_x = self.x()

        self.model.moving = self.dragging or self.driving

        self.model.step(dt, dx)

        # is the mouse on the car?
        inside = False

        if self.isVisible() and not self.driving and not self.dragging:

            local = self.mapFromGlobal(self._cursor())

            inside = self._hover_zone().contains(local)

            self._hovered_button = self._button_at(local) if self.interact > 0.5 else None

        else:

            self._hovered_button = None

        if inside:

            self._inside = True
            self._leave_at = 0.0

        elif self._inside:

            if self._leave_at == 0.0:
                self._leave_at = self._now + LEAVE_LINGER_MS / 1000

            if self._now >= self._leave_at:

                self._inside = False
                self._leave_at = 0.0

        target = 1.0 if (self._inside and not self.dragging and not self.driving) else 0.0

        self.interact += (target - self.interact) * (1 - 2.718 ** (-12 * dt))

        self.model.hover = self.interact > 0.4

        if self.isVisible():
            self.update()

    def _button_at(self, point):

        for i in range(3):

            if self.button_rect(i).adjusted(-6, -6, 6, 6).contains(point):
                return i

        return None

    # ------------------------------------------------
    # Painting
    # ------------------------------------------------

    def paintEvent(self, event):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # an almost invisible layer so the whole car area receives the
        # mouse (fully transparent pixels let clicks fall through)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 3))
        painter.drawRect(CAR_HIT)

        draw_car(painter, QRectF(CAR_RECT), self.model)

        if self.interact > 0.02:
            self._draw_buttons(painter)

        painter.end()

    def _draw_buttons(self, painter):

        t = self.interact

        # ease out with a little overshoot, and slide up from the car
        slide = (1 - t) * 14

        painter.setOpacity(min(1.0, t * 1.3))

        for i, label in enumerate(BUTTON_LABELS):

            rect = QRectF(self.button_rect(i)).translated(0, slide)

            hovered = self._hovered_button == i
            pressed = self._pressed_button == i
            active = label == "Voice" and self.listening

            scale = 1.0 + (0.12 if hovered else 0.0) - (0.06 if pressed else 0.0)

            painter.save()
            painter.translate(rect.center())
            painter.scale(scale, scale)
            painter.translate(-rect.center())

            fill = QColor("#ff5c6c") if active else QColor(YELLOW if hovered else theme.PANEL)

            painter.setPen(QPen(QColor(theme.BORDER if not hovered else YELLOW), 1.2))
            painter.setBrush(fill)
            painter.drawEllipse(rect)

            icon_color = "#1a1a1f" if (hovered or active) else "#f1f3f8"

            _draw_icon(painter, label, rect.center().toPoint(), icon_color)

            painter.restore()

            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            painter.setPen(QColor(theme.MUTED if not hovered else theme.TEXT))

            painter.drawText(
                QRectF(rect.left() - 10, rect.bottom() + 4, rect.width() + 20, 14),
                Qt.AlignCenter,
                label,
            )

        painter.setOpacity(1.0)

    # ------------------------------------------------
    # Mouse
    # ------------------------------------------------

    def mousePressEvent(self, event):

        if event.button() != Qt.LeftButton or self.driving:
            return

        point = event.position().toPoint()

        button = self._button_at(point) if self.interact > 0.6 else None

        if button is not None:

            self._pressed_button = button

            return

        if CAR_HIT.contains(point):

            self.dragging = True
            self._grab_offset = event.globalPosition().toPoint() - QPoint(self.x(), self.y())
            self.card.dismiss()

    def mouseMoveEvent(self, event):

        if self.dragging:

            target = event.globalPosition().toPoint() - self._grab_offset

            self.move(clamp_to_screens(target, self.size()))

    def mouseReleaseEvent(self, event):

        if event.button() != Qt.LeftButton:
            return

        if self.dragging:

            self.dragging = False

            self.save_position()

            self._face_the_middle()

            self.model.kick("bounce")

            return

        pressed, self._pressed_button = self._pressed_button, None

        point = event.position().toPoint()

        if pressed is not None and self._button_at(point) == pressed:

            if pressed == 0:
                self.voice_requested.emit()

            elif pressed == 1:
                self.chat_requested.emit()

            else:
                self.hide_requested.emit()

    # ------------------------------------------------
    # Answers
    # ------------------------------------------------

    def say(self, text, confirm=False, allow_always=False):
        """
        Show a reply in a card above the car.
        """

        if self.dragging or self.driving:
            return

        anchor = QRect(self.x() + CAR_HIT.x(), self.y() + CAR_HIT.y(), CAR_HIT.width(), CAR_HIT.height())

        self.card.show_message(text, anchor, confirm, allow_always)

    # ------------------------------------------------
    # Menu
    # ------------------------------------------------

    def contextMenuEvent(self, event):

        menu = QMenu(self)

        chat = menu.addAction("Open chat")
        chat.triggered.connect(self.chat_requested)

        talk = menu.addAction("Talk")
        talk.triggered.connect(self.voice_requested)

        hide = menu.addAction("Hide (Alt+S brings it back)")
        hide.triggered.connect(self.hide_requested)

        menu.addSeparator()

        if self.voice_replies_action is not None:
            menu.addAction(self.voice_replies_action)

        if self.hands_free_action is not None:
            menu.addAction(self.hands_free_action)

        reset = menu.addAction("Reset position")
        reset.triggered.connect(self.reset_position)

        menu.addSeparator()

        quit_action = menu.addAction("Quit Sophia")
        quit_action.triggered.connect(self.quit_requested)

        menu.exec(event.globalPos())

    def closeEvent(self, event):

        self.card.close()

        super().closeEvent(event)


def dock_beside(window, car_rect):
    """
    Put the chat window next to the car (on the side with more room),
    kept on screen.
    """

    rects = screen_rects()

    if not rects:
        return

    area = nearest_rect(car_rect.center(), rects)

    size = window.size()

    gap = 10

    if car_rect.center().x() > area.center().x():
        x = car_rect.left() - size.width() - gap

    else:
        x = car_rect.right() + gap

    y = car_rect.center().y() - size.height() // 2

    window.move(clamp_to_screens(QPoint(x, y), size, rects))


class CarController(QObject):
    """
    Connects the floating car to the chat window (which holds Sophia).
    """

    def __init__(self, window, car):

        super().__init__()

        self.window = window
        self.car = car

        window.activity_listeners.append(car.set_activity)
        window.effect_listeners.append(car.model.kick)
        window.hide_on_close = True

        car.voice_requested.connect(self.listen)
        car.chat_requested.connect(self.open_chat)
        car.hide_requested.connect(car.hide_away)
        car.quit_requested.connect(self.quit)

        car.card.answered.connect(self._answer)

        window.replied.connect(self._on_reply)
        window.hint.connect(self._on_hint)

        car.voice_replies_action = window.voice_toggle_action()
        car.hands_free_action = window.hands_free_action

    # ------------------------------------------------

    def listen(self):

        self.window.start_voice_turn()

    def open_chat(self):

        self.car.card.dismiss()

        rect = QRect(self.car.x() + CAR_HIT.x(), self.car.y() + CAR_HIT.y(), CAR_HIT.width(), CAR_HIT.height())

        dock_beside(self.window, rect)

        self.window.bring_to_front()

    def quit(self):

        self.car.exit_and_quit(self.window.quit)

    def _answer(self, answer):

        self.window.send(answer)

    def _on_reply(self, text, confirm, allow_always):

        # with the chat open, the reply is already there
        if self.window.isVisible():
            return

        self.car.say(text, confirm, allow_always)

    def _on_hint(self, text):

        if not self.window.isVisible():
            self.car.say(text)

    def hotkey(self):

        self.listen()
