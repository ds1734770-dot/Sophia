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
import math

from PySide6.QtCore import (
    QPointF,
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
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QToolTip,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.car import CANVAS_W, STATES, CarModel, draw_car
from app.ui.characters import CHARACTERS, make_model, valid

log = logging.getLogger("sophia.ui")

DEFAULT_WIDTH = 130      # the window (and the car drawing) is this wide
MIN_WIDTH = 70
MAX_WIDTH = 300

SIZES = {"Tiny": 96, "Small": 130, "Medium": 180, "Large": 250}

BUTTON_LABELS = ("Voice", "Chat", "Hide")


class Layout:
    """
    All sizes in the window, scaled from its width. At 300 the car is
    drawn at the size of the first version; the default is much smaller.
    """

    def __init__(self, width, character="car"):

        width = max(MIN_WIDTH, min(MAX_WIDTH, int(width)))

        k = width / 300

        self.width = width
        self.height = round(236 * k)

        if character != "car":

            self._tall(width, k, character)

            return

        # where the car is drawn, and the part that counts as "on the car"
        self.car_rect = QRect(0, round(22 * k), width, round(106 * k))
        self.car_hit = QRect(round(26 * k), round(40 * k), round(248 * k), round(92 * k))

        # three small round buttons below the car
        self.button = max(15, round(42 * k * 0.8))
        self.gap = max(5, round(16 * k * 0.8))
        self.button_y = round(138 * k) + 6

        # canvas pixels per screen pixel (for wheel rotation)
        self.logical_per_pixel = CANVAS_W / width


def _tall(self, width, k, character):
        """
        A standing figure: the drawing is taller than wide, with the
        buttons under its feet.
        """

        from app.ui.characters import CHARACTERS

        canvas_w, canvas_h = CHARACTERS[character]["model"].canvas

        drawn = round(width * canvas_h / canvas_w)

        self.car_rect = QRect(0, round(4 * k), width, drawn)
        self.car_hit = QRect(
            round(width * 0.24), self.car_rect.top() + round(drawn * 0.06),
            round(width * 0.52), round(drawn * 0.9),
        )

        self.button = max(15, round(42 * k * 0.8))
        self.gap = max(5, round(16 * k * 0.8))
        self.button_y = self.car_rect.bottom() + 4

        self.height = self.button_y + self.button + 12

        self.logical_per_pixel = canvas_w / width


Layout._tall = _tall


FRAME_MS = 16
LEAVE_LINGER_MS = 650

ENTRY_MS = 1150
HIDE_MS = 700
REV_MS = 500
EXIT_MS = 850

# the armor: fly in, brake on the palm repulsors, drop, touch down
ARMOR_ENTRY_MS = 2500
ARMOR_SETTLE_MS = 650
ARMOR_CHARGE_MS = 480
ARMOR_LAUNCH_MS = 1150


def lerp_point(a, b, e):

    return QPoint(round(a.x() + (b.x() - a.x()) * e), round(a.y() + (b.y() - a.y()) * e))

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

def _draw_icon(painter, kind, center, color, size=42):
    """
    Small line icons drawn in code (mic, chat, hide), scaled to the
    button they sit in.
    """

    painter.save()
    painter.translate(center)
    painter.scale(size / 42, size / 42)

    pen = QPen(QColor(color), 3.2)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)

    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    if kind == "Voice":

        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(-4.5, -11, 9, 15), 4.5, 4.5)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(QRectF(-9, -8, 18, 15), 200 * 16, 140 * 16)
        painter.drawLine(0, 7, 0, 12)
        painter.drawLine(-4, 12, 4, 12)

    elif kind == "Chat":

        path = QPainterPath()
        path.addRoundedRect(QRectF(-11, -10, 22, 16), 6, 6)
        path.moveTo(-5, 6)
        path.lineTo(-8, 12)
        path.lineTo(1, 6)

        painter.drawPath(path)

        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)

        for dx in (-5, 0, 5):
            painter.drawEllipse(QPointF(dx, -2), 1.3, 1.3)

    else:   # Hide

        painter.drawLine(-8, -4, 0, 4)
        painter.drawLine(0, 4, 8, -4)
        painter.drawLine(-9, 10, 9, 10)

    painter.restore()


# ---------------------------------------------------------------
# The car window
# ---------------------------------------------------------------

class FloatingCar(QWidget):

    voice_requested = Signal()
    chat_requested = Signal()
    hide_requested = Signal()
    quit_requested = Signal()
    appearance_requested = Signal(str)

    def __init__(self, settings=None, cursor=QCursor.pos, sounds=None, width=None):

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

        self.character = valid(self.settings.value("appearance", "car"))

        self.model = make_model(self.character)

        saved_width = self.settings.value("car_width")

        try:
            start_width = int(width or saved_width or DEFAULT_WIDTH)

        except (TypeError, ValueError):
            start_width = DEFAULT_WIDTH

        self.lay = Layout(start_width, self.character)

        self.setFixedSize(self.lay.width, self.lay.height)

        # sound effects (any object with play(name)); None is silent
        self.sounds = sounds
        self._was_interacting = False
        self.suppress_listen_chime = False
        self._quiet_arrival = False
        self.sound_action = None

        if sounds is not None:

            from PySide6.QtGui import QAction

            self.sound_action = QAction("Sound effects", self)
            self.sound_action.setCheckable(True)
            self.sound_action.setChecked(self.settings.value("sounds", True, type=bool))
            self.sound_action.toggled.connect(self._set_sounds)

            sounds.set_enabled(self.sound_action.isChecked())

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

        area = nearest_rect(self.rest_pos + QPoint(self.lay.width // 2, self.lay.height // 2))

        self.model.facing = -1 if self.rest_pos.x() + self.lay.width // 2 > area.center().x() else 1

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

        area = nearest_rect(target + QPoint(self.lay.width // 2, self.lay.height // 2))

        from_left = target.x() + self.lay.width // 2 < area.center().x()

        x = area.left() - self.lay.width - 20 if from_left else area.right() + 20

        return QPoint(x, target.y()), from_left

    # ------------------------------------------------
    # The armor's flights
    # ------------------------------------------------

    def _sequence(self, ms, frame, done):
        """
        Run frame(u) for u from 0 to 1 over ms milliseconds, then done().
        The window counts as "driving" meanwhile, so it cannot be dragged.
        """

        if self._animation is not None:
            self._animation.stop()

        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(ms)
        animation.setEasingCurve(QEasingCurve.Linear)
        animation.valueChanged.connect(lambda u: frame(float(u)))
        animation.finished.connect(done)

        self.driving = True

        animation.start()

        self._animation = animation

    def _armor_enter(self, quiet):
        """
        Fly in on full thrust from above the nearest screen edge, brake
        with the palm repulsors, drop, and touch down.
        """

        lay = self.lay

        land = QPoint(self.rest_pos)

        area = nearest_rect(land + QPoint(lay.width // 2, lay.height // 2))

        from_left = land.x() + lay.width // 2 < area.center().x()

        d = 1 if from_left else -1

        start = QPoint(
            area.left() - lay.width - 40 if from_left else area.right() + 40,
            land.y() - 260,
        )
        approach_point = QPoint(land.x() - d * int(lay.width * 0.9), land.y() - 120)
        hover_point = QPoint(land.x(), land.y() - 28)

        model = self.model

        model.facing = d
        model.begin("arrive")
        model.set_phase("fly")

        self.move(start)
        self._last_x = start.x()

        self.show()

        if not quiet:

            self._play("jet")

            QTimer.singleShot(int(ARMOR_ENTRY_MS * 0.5), lambda: self._play("repulsor"))

        def frame(u):

            if u < 0.5:

                v = u / 0.5
                point = lerp_point(start, approach_point, 1 - (1 - v) ** 2.2)
                phase = "fly"

            elif u < 0.8:

                v = (u - 0.5) / 0.3
                point = lerp_point(approach_point, hover_point, 0.5 - 0.5 * math.cos(math.pi * v))
                phase = "brake"

            else:

                v = (u - 0.8) / 0.2
                point = lerp_point(hover_point, land, v * v)
                phase = "land"

            model.set_phase(phase)

            self.move(point)

        def touched_down():

            self.move(land)

            model.set_phase("touch")

            if not quiet:
                self._play("land")

            QTimer.singleShot(ARMOR_SETTLE_MS, settled)

        def settled():

            model.end_sequence()

            self.driving = False

            self._face_the_middle()

        self._sequence(ARMOR_ENTRY_MS, frame, touched_down)

    def _armor_depart(self, done, force_right=False, quiet=False):
        """
        Crouch and charge the palms, then launch up and away off the
        nearest screen edge (or the right edge). done() is called once
        the suit has gone.
        """

        lay = self.lay
        model = self.model

        start = QPoint(self.x(), self.y())

        area = nearest_rect(start + QPoint(lay.width // 2, lay.height // 2))

        right = force_right or start.x() + lay.width // 2 > area.center().x()

        end = QPoint(
            area.right() + 60 if right else area.left() - lay.width - 60,
            start.y() - 340,
        )

        model.facing = 1 if right else -1
        model.begin("depart")
        model.set_phase("charge")

        self.driving = True

        if not quiet:
            self._play("repulsor")

        def launch():

            model.set_phase("launch")

            if not quiet:
                self._play("launch")

            def frame(u):

                # straight up first, then away on a climbing diagonal
                x = start.x() + (end.x() - start.x()) * u ** 2.6
                y = start.y() + (end.y() - start.y()) * u ** 1.5

                self.move(QPoint(round(x), round(y)))

            def finished():

                model.end_sequence()

                self.driving = False

                done()

            self._sequence(ARMOR_LAUNCH_MS, frame, finished)

        QTimer.singleShot(ARMOR_CHARGE_MS, launch)

    def enter(self, quiet=False):
        """
        Drive in from the nearest screen edge and park. quiet skips the
        engine and honk sounds (the microphone would hear them).
        """

        self.hidden = False

        if self.character == "armor":

            self._quiet_arrival = quiet

            self._armor_enter(quiet)

            return

        if not quiet:
            self._play("entry")

        self._quiet_arrival = quiet

        start, from_left = self._edge_start(self.rest_pos)

        self.model.facing = 1 if from_left else -1

        self.move(start)
        self._last_x = start.x()

        self.show()

        def arrived():

            if not self._quiet_arrival:
                self._play("honk")

            self.model.kick("honk")
            self.model.kick("bounce")
            self.model.kick("wipe")

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

        if self.character == "armor":

            self._armor_depart(self.hide)

            return

        self._play("hide")

        target, from_left = self._edge_start(QPoint(self.x(), self.y()))

        # leave by the same side it would enter from
        self.model.facing = -1 if from_left else 1

        def gone():

            self.hide()

        self._drive(QPoint(self.x(), self.y()), target, HIDE_MS, QEasingCurve.InCubic, gone)

    def show_back(self, quiet=False):

        if self.hidden or not self.isVisible():
            self.enter(quiet=quiet)

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

        if self.character == "armor":

            self._armor_depart(done, force_right=True)

            return

        self._play("exit")

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

    def on_effect(self, kind):
        """
        An effect requested by the chat window (a task finished, an
        error...): show it on the car, with its sound.
        """

        self.model.kick(kind)

        if kind == "burst":
            self._play("success")

        elif kind == "honk":
            self._play("honk")

    def _set_sounds(self, on):

        self.settings.setValue("sounds", on)

        if self.sounds is not None:

            self.sounds.set_enabled(on)

            if on:
                self._play("click")

    def _play(self, name):

        if self.sounds is not None:

            try:
                self.sounds.play(name)

            except Exception:
                log.exception("Sound failed")

    def set_activity(self, state, level):
        """
        What Sophia is doing (from the chat window): idle, listening,
        thinking, speaking or alert.
        """

        if state in STATES:

            if state == "listening" and not self.listening:

                # after the wake word there is no chime: the microphone
                # is already open and would record it
                if self.suppress_listen_chime:
                    self.suppress_listen_chime = False

                else:
                    self._play("listen")

            if state == "thinking" and self.model.state != "thinking":
                self._play("wiper")

            self.model.set_state(state)
            self.model.set_level(level)

            self.listening = state == "listening"

    def car_screen_rect(self):
        """
        The car's body in screen coordinates.
        """

        hit = self.lay.car_hit

        return QRect(self.x() + hit.x(), self.y() + hit.y(), hit.width(), hit.height())

    def _hover_zone(self):

        zone = QRect(self.lay.car_hit)

        if self.interact > 0.05:
            zone = zone.united(self._buttons_zone())

        return zone

    def _buttons_zone(self):

        lay = self.lay

        total = 3 * lay.button + 2 * lay.gap

        return QRect((lay.width - total) // 2 - 6, lay.button_y - 8, total + 12, lay.button + 16)

    def button_rect(self, index):

        lay = self.lay

        total = 3 * lay.button + 2 * lay.gap

        x = (lay.width - total) // 2 + index * (lay.button + lay.gap)

        return QRect(x, lay.button_y, lay.button, lay.button)

    def set_character(self, name):
        """
        Change appearance (car, armor...). The figure stays where it
        stands: its bottom centre does not move.
        """

        name = valid(name)

        self.settings.setValue("appearance", name)

        if name == self.character:
            return

        old = self.lay
        old_model = self.model

        foot = QPoint(self.x() + old.width // 2, self.y() + old.height)

        self.character = name
        self.model = make_model(name)

        # keep what the figure was doing and wearing
        self.model.facing = old_model.facing
        self.model.hover = old_model.hover
        self.model.state = old_model.state
        self.model.attention = old_model.attention
        self.model.pips = list(old_model.pips)
        self.model.set_tint(
            old_model._tint_goal.name() if old_model._tint_goal is not None else None
        )

        self.lay = Layout(old.width, name)

        self.setFixedSize(self.lay.width, self.lay.height)

        self.move(clamp_to_screens(
            QPoint(foot.x() - self.lay.width // 2, foot.y() - self.lay.height),
            self.size(),
        ))

        self.save_position()
        self._last_x = self.x()

        self.update()

    def set_width(self, width):
        """
        Resize the whole car (keeps its centre where it was).
        """

        old = self.lay

        self.lay = Layout(width, self.character)

        self.settings.setValue("car_width", self.lay.width)

        center = QPoint(self.x() + old.width // 2, self.y() + old.height // 2)

        self.setFixedSize(self.lay.width, self.lay.height)

        self.move(clamp_to_screens(
            QPoint(center.x() - self.lay.width // 2, center.y() - self.lay.height // 2),
            self.size(),
        ))

        self.save_position()
        self._last_x = self.x()

        self.update()

    def _tick(self):

        dt = self._clock.restart() / 1000

        self._now += dt

        # driving: tell the model how far we moved (in canvas pixels)
        dx = (self.x() - self._last_x) * self.lay.logical_per_pixel

        self._last_x = self.x()

        self.model.moving = self.dragging or self.driving

        self.model.step(dt, dx)

        # is the mouse on the car?
        inside = False

        if self.isVisible() and not self.driving and not self.dragging:

            local = self.mapFromGlobal(self._cursor())

            inside = self._hover_zone().contains(local)

            hovered = self._button_at(local) if self.interact > 0.5 else None

            if hovered != self._hovered_button and hovered is not None:

                QToolTip.showText(
                    self._cursor() + QPoint(0, 18), BUTTON_LABELS[hovered], self
                )

            self._hovered_button = hovered

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

        if self.model.hover and not self._was_interacting:

            self.model.kick("wipe")

        self._was_interacting = self.model.hover

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
        painter.drawRect(self.lay.car_hit)

        self.model.draw(painter, QRectF(self.lay.car_rect))

        if self.interact > 0.02:
            self._draw_buttons(painter)

        painter.end()

    def _draw_buttons(self, painter):

        t = self.interact

        # slide up from under the car as they appear
        slide = (1 - t) * 6

        painter.setOpacity(min(1.0, t * 1.3))

        for i, label in enumerate(BUTTON_LABELS):

            rect = QRectF(self.button_rect(i)).translated(0, slide)

            hovered = self._hovered_button == i
            pressed = self._pressed_button == i
            active = label == "Voice" and self.listening

            scale = 1.0 + (0.15 if hovered else 0.0) - (0.08 if pressed else 0.0)

            painter.save()
            painter.translate(rect.center())
            painter.scale(scale, scale)
            painter.translate(-rect.center())

            fill = QColor("#ff5c6c") if active else QColor(YELLOW if hovered else theme.PANEL)

            painter.setPen(QPen(QColor(theme.BORDER if not hovered else YELLOW), 1.0))
            painter.setBrush(fill)
            painter.drawEllipse(rect)

            icon_color = "#1a1a1f" if (hovered or active) else "#f1f3f8"

            _draw_icon(painter, label, rect.center(), icon_color, rect.width())

            painter.restore()

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

        if self.lay.car_hit.contains(point):

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

            self._play("click")

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

        anchor = self.car_screen_rect()

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

        looks = menu.addMenu("Appearance")

        for key, info in CHARACTERS.items():

            action = looks.addAction(info["label"])
            action.setCheckable(True)
            action.setChecked(key == self.character)
            action.triggered.connect(lambda _=False, k=key: self.appearance_requested.emit(k))

        sizes = menu.addMenu("Size")

        for label, width in SIZES.items():

            action = sizes.addAction(label)
            action.setCheckable(True)
            action.setChecked(abs(self.lay.width - width) < 8)
            action.triggered.connect(lambda _=False, w=width: self.set_width(w))

        if self.sound_action is not None:
            menu.addAction(self.sound_action)

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

        # owned by the window, so it lives as long as the app does
        super().__init__(window)

        self.window = window
        self.car = car

        window.activity_listeners.append(car.set_activity)
        window.effect_listeners.append(car.on_effect)
        window.hide_on_close = True

        car.voice_requested.connect(self.listen)
        car.chat_requested.connect(self.open_chat)
        car.hide_requested.connect(car.hide_away)
        car.quit_requested.connect(self.quit)

        # the chosen appearance applies to the car window and the chat
        car.appearance_requested.connect(self.set_appearance)
        window.appearance_requested.connect(self.set_appearance)

        window._has_car = True
        window.set_appearance(car.character)

        car.card.answered.connect(self._answer)

        window.wake_activated.connect(self._on_wake)

        # other agents (Claude, ChatGPT, Gemini...): the car takes the
        # colour of the one that matters and reacts to what they report
        self._agent_task = None

        if getattr(window, "agent_hub", None) is not None:
            window.agent_signal.connect(self._on_agent)

        window.replied.connect(self._on_reply)
        window.hint.connect(self._on_hint)

        car.voice_replies_action = window.voice_toggle_action()
        car.hands_free_action = window.hands_free_action

    # ------------------------------------------------

    def listen(self):

        self.window.start_voice_turn()

    def _on_wake(self):
        """
        The wake word was heard: come out of hiding (silently, so the
        microphone hears only the user) and clear any old answer.
        """

        self.car.suppress_listen_chime = True

        self.car.card.dismiss()

        if self.car.hidden or not self.car.isVisible():
            self.car.show_back(quiet=True)

    def open_chat(self):

        self.car.card.dismiss()

        rect = self.car.car_screen_rect()

        dock_beside(self.window, rect)

        self.window.bring_to_front()

    def quit(self):

        self.car.exit_and_quit(self.window.quit)

    def _answer(self, answer):

        # a yes / no on the card may be for an agent's question
        if self._agent_task is not None:

            task_id, self._agent_task = self._agent_task, None

            self.window.reply_to_agent(task_id, answer)

            return

        self.window.send(answer)

    # ------------------------------------------------
    # Other agents
    # ------------------------------------------------

    def _paint_for_agents(self):
        """
        Dress the car for the agent that matters most right now, and show
        the others as dots.
        """

        hub = self.window.agent_hub

        lead = hub.lead()

        others = [
            t.color for t in hub.with_status("needs_input", "running")
            if lead is None or t.id != lead.id
        ]

        waiting = bool(hub.with_status("needs_input"))

        for model in (self.car.model, self.window.orb_model):

            model.set_tint(lead.color if lead else None)
            model.attention = waiting
            model.pips = others[:6]

    def set_appearance(self, name):

        self.car.set_character(name)

        self.window.set_appearance(name)

        if getattr(self.window, "agent_hub", None) is not None:
            self._paint_for_agents()

    def _on_agent(self, kind, task, previous):

        self._paint_for_agents()

        status = task.status

        if status == previous and kind != "started":
            return

        name = f"**{task.label}**"
        what = task.title or task.project

        if status == "needs_input":

            # this one matters: come out of hiding and get attention
            if self.car.hidden or not self.car.isVisible():
                self.car.show_back()

            self.car.on_effect("honk")

            from app.ui.agents_panel import is_yes_no

            yes_no = is_yes_no(task.question)

            self._agent_task = task.id if yes_no else None

            self.car.say(
                f"{name} needs you: {task.question}"
                + ("" if yes_no else "\n\n*Click here to reply.*"),
                confirm=yes_no,
            )

        elif status == "done":

            self.car.on_effect("burst")

            if self.car.isVisible() and not self.car.hidden:
                self.car.say(f"✓ {name} finished" + (f": {what}" if what else "."))

        elif status == "failed":

            self.car.on_effect("shake")

            if self.car.isVisible() and not self.car.hidden:
                self.car.say(f"✕ {name} hit a problem" + (f" with {what}" if what else "."))

        elif kind == "started":

            self.car.on_effect("bounce")

    def _on_reply(self, text, confirm, allow_always):

        # Sophia's own question replaces any agent question on the card
        self._agent_task = None

        # with the chat open, the reply is already there
        if self.window.isVisible():
            return

        self.car.say(text, confirm, allow_always)

    def _on_hint(self, text):

        if not self.window.isVisible():
            self.car.say(text)

    def hotkey(self):

        self.listen()
