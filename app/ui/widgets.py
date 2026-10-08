import math
import re
import time

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    QPropertyAnimation,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

BUBBLE_WIDTH_RATIO = 0.78

# Typing reveal: words added per tick (every REVEAL_MS) by reply length
REVEAL_MS = 22
LONG_REPLY_CHARS = 700


def fade_in(widget, duration=260):
    """
    Fade a widget in. The animation is kept on the widget so it is not
    garbage collected.
    """

    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)

    widget.setGraphicsEffect(effect)

    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)

    # drop the effect afterwards: it makes text rendering softer
    animation.finished.connect(lambda: widget.setGraphicsEffect(None))

    animation.start()

    widget._fade = animation

    return animation


def collapse(widget, duration=420, on_done=None):
    """
    Animate a widget's height to zero, then hide it.
    """

    widget.setMinimumHeight(0)

    animation = QPropertyAnimation(widget, b"maximumHeight", widget)
    animation.setDuration(duration)
    animation.setStartValue(widget.height())
    animation.setEndValue(0)
    animation.setEasingCurve(QEasingCurve.InOutCubic)

    def done():

        widget.hide()

        if on_done is not None:
            on_done()

    animation.finished.connect(done)
    animation.start()

    widget._collapse = animation

    return animation


class ThinkingDots(QWidget):
    """
    Three dots that bounce in a wave.
    """

    def __init__(self):

        super().__init__()

        self.setFixedSize(46, 22)

        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

    def _tick(self):

        self._phase += 0.22
        self.update()

    def paintEvent(self, event):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        for i in range(3):

            lift = max(0.0, math.sin(self._phase - i * 0.9))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(139, 146, 165, int(120 + 135 * lift)))

            painter.drawEllipse(8 + i * 15 - 3, int(11 - 6 * lift) - 3, 7, 7)

        painter.end()


class Bubble(QFrame):
    """
    One chat message. role: "user", "bot" or "note".
    """

    def __init__(self, text, role="bot", dots=False):

        super().__init__()

        self.role = role
        self.setObjectName(f"bubble_{role}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)

        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.MarkdownText)
        self.label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        # Replies can contain file names and web text: never open links
        self.label.setOpenExternalLinks(False)

        layout.addWidget(self.label)

        self._full = ""
        self._timer = None

        self.dots = None

        # hover to copy: floats in the corner, so the bubble never resizes
        self.copy_button = None

        if role == "bot" and not dots:

            self.copy_button = QPushButton("Copy", self)
            self.copy_button.setObjectName("copy")
            self.copy_button.setCursor(Qt.PointingHandCursor)
            self.copy_button.setFixedSize(46, 22)
            self.copy_button.clicked.connect(self._copy)
            self.copy_button.hide()

        if dots:

            self.dots = ThinkingDots()
            layout.addWidget(self.dots)
            self.label.hide()

        else:

            self.set_text(text)

    # ------------------------------------------------

    def _copy(self):

        QApplication.clipboard().setText(self._full)

        self.copy_button.setText("Copied")

        QTimer.singleShot(1200, lambda: self.copy_button.setText("Copy"))

    def enterEvent(self, event):

        if self.copy_button is not None and self._full.strip():

            self.copy_button.move(self.width() - 52, 4)
            self.copy_button.show()
            self.copy_button.raise_()

        super().enterEvent(event)

    def leaveEvent(self, event):

        if self.copy_button is not None:
            self.copy_button.hide()

        super().leaveEvent(event)

    def set_text(self, text):

        self._stop_reveal()

        self._full = text
        self.label.setText(text)

    def text(self):
        """
        The whole message, even while it is still being revealed.
        """

        return self._full

    def reveal(self, text):
        """
        Show the text word by word, like it is being typed.
        """

        self._stop_reveal()

        self._full = text

        words = re.findall(r"\S+\s*", text)

        if len(words) < 3:

            self.label.setText(text)

            return

        step = 1 if len(text) < LONG_REPLY_CHARS else max(2, len(words) // 60)

        self._shown = 0
        self._words = words
        self._step = step

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._reveal_more)
        self._timer.start(REVEAL_MS)

        self._reveal_more()

    def _reveal_more(self):

        self._shown = min(len(self._words), self._shown + self._step)

        self.label.setText("".join(self._words[:self._shown]))

        if self._shown >= len(self._words):

            self._stop_reveal()
            self.label.setText(self._full)

    def _stop_reveal(self):

        if self._timer is not None:

            self._timer.stop()
            self._timer = None

    def fit(self, max_width):
        """
        Size the bubble to its text, up to max_width. (A word-wrapped
        label on its own would collapse to a narrow column.)
        """

        metrics = self.label.fontMetrics()

        widest = max(
            (metrics.horizontalAdvance(line) for line in self._full.split("\n")),
            default=0,
        )

        # padding, plus room for list bullets and bold text
        wanted = widest + 28 + 36

        if self.dots is not None:
            wanted = 76

        self.setFixedWidth(max(60, min(max_width, wanted)))


# ---------------------------------------------------------------
# Agent look: avatar, status pill, live steps
# ---------------------------------------------------------------

AMBER = QColor("#ffb800")
GREEN = QColor("#3ddc97")
RED = QColor("#ff6b6b")
MUTED_COLOR = QColor("#8a93a6")


class Avatar(QWidget):
    """
    Sophia's mark next to her messages: the car on a dark disc with a
    thin amber ring.
    """

    SIZE = 30

    def __init__(self, pixmap=None):

        super().__init__()

        self.pixmap = pixmap
        self.setFixedSize(self.SIZE, self.SIZE)

    def paintEvent(self, event):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        size = self.SIZE
        rect = QRectF(1, 1, size - 2, size - 2)

        gradient = QLinearGradient(0, 0, size, size)
        gradient.setColorAt(0, QColor("#232837"))
        gradient.setColorAt(1, QColor("#12151d"))

        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(255, 184, 0, 150), 1.4))
        painter.drawEllipse(rect)

        if self.pixmap is not None:

            inner = size - 8

            painter.setClipPath(self._disc(rect))
            painter.drawPixmap(
                QRectF(4, 4, inner, inner).toRect(), self.pixmap
            )

        else:

            painter.setPen(Qt.NoPen)
            painter.setBrush(AMBER)
            painter.drawEllipse(QRectF(size / 2 - 4, size / 2 - 4, 8, 8))

        painter.end()

    @staticmethod
    def _disc(rect):

        from PySide6.QtGui import QPainterPath

        path = QPainterPath()
        path.addEllipse(rect)

        return path


class StatusPill(QLabel):
    """
    The header's status: a coloured dot and the words. The colour follows
    what Sophia is doing (idle, working, listening, a problem).
    """

    WORKING = ("thinking", "answering", "transcrib", "starting", "working")
    LISTENING = ("listening",)
    PROBLEM = ("didn't", "not running", "couldn't", "failed")

    def __init__(self, text=""):

        super().__init__(text)

        self.setObjectName("status")
        self.setProperty("state", "idle")

        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse)

    @classmethod
    def classify(cls, text):

        low = text.lower()

        if any(w in low for w in cls.PROBLEM):
            return "problem"

        if any(w in low for w in cls.LISTENING) and "for" not in low:
            return "listening"

        if any(w in low for w in cls.WORKING):
            return "working"

        return "idle"

    def setText(self, text):

        super().setText(text)

        state = self.classify(text)

        if state != self.property("state"):

            self.setProperty("state", state)

            self.style().unpolish(self)
            self.style().polish(self)

        if state in ("working", "listening") and not self._timer.isActive():
            self._timer.start(50)

        elif state not in ("working", "listening"):
            self._timer.stop()

        self.setVisible(bool(text))
        self.update()

    def _pulse(self):

        self._phase += 0.15
        self.update()

    def paintEvent(self, event):

        super().paintEvent(event)

        state = self.property("state")

        color = {
            "idle": GREEN, "working": AMBER, "listening": GREEN, "problem": RED,
        }.get(state, MUTED_COLOR)

        pulse = 0.0

        if state in ("working", "listening"):
            pulse = (math.sin(self._phase) + 1) / 2

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        centre = QPointF(12, self.height() / 2)

        if pulse:

            halo = QColor(color)
            halo.setAlpha(int(70 * pulse))

            painter.setPen(Qt.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(centre, 3.5 + 3 * pulse, 3.5 + 3 * pulse)

        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(centre, 3.2, 3.2)

        painter.end()


class StepGlyph(QWidget):
    """
    The state of one step: a spinning arc while it runs, then a tick or
    a cross.
    """

    def __init__(self):

        super().__init__()

        self.setFixedSize(18, 18)

        self.mode = "running"
        self._angle = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._spin)
        self._timer.start(30)

    def _spin(self):

        self._angle = (self._angle + 18) % 360
        self.update()

    def set_mode(self, mode):

        self.mode = mode

        if mode != "running":
            self._timer.stop()

        self.update()

    def paintEvent(self, event):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(3, 3, 12, 12)

        if self.mode == "running":

            painter.setPen(QPen(QColor(255, 184, 0, 60), 2))
            painter.drawEllipse(rect)

            painter.setPen(QPen(AMBER, 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(rect, -self._angle * 16, 100 * 16)

        elif self.mode == "ok":

            painter.setPen(QPen(GREEN, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolyline([QPointF(4, 9.5), QPointF(7.5, 13), QPointF(14, 5.5)])

        else:

            painter.setPen(QPen(RED, 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(5, 5), QPointF(13, 13))
            painter.drawLine(QPointF(13, 5), QPointF(5, 13))

        painter.end()


class StepRow(QWidget):

    def __init__(self, icon, text):

        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self.glyph = StepGlyph()

        self.label = QLabel(f"{icon}  {text}")
        self.label.setObjectName("step_text")
        self.label.setWordWrap(True)

        self.time = QLabel("")
        self.time.setObjectName("step_time")

        layout.addWidget(self.glyph)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.time)

        self.started = time.monotonic()
        self.finished = False
        self.ok = True

    def finish(self, ok, seconds, detail=""):

        self.finished = True
        self.ok = ok

        self.glyph.set_mode("ok" if ok else "fail")
        self.time.setText(f"{seconds:.1f}s" if seconds >= 0.05 else "")

        if not ok and detail:
            self.label.setToolTip(detail)


class AgentSteps(QFrame):
    """
    What Sophia is doing right now, one line per action with a live
    spinner, folding into a one-line summary when she is done ("Used 3
    actions"). Click the header to open or close the list.
    """

    def __init__(self):

        super().__init__()

        self.setObjectName("steps")
        self.setMinimumWidth(380)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(4)

        head = QWidget()
        head.setCursor(Qt.PointingHandCursor)

        row = QHBoxLayout(head)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.glyph = StepGlyph()

        self.title = QLabel("Working…")
        self.title.setObjectName("steps_title")

        self.meta = QLabel("")
        self.meta.setObjectName("step_time")

        self.chevron = QLabel("▾")
        self.chevron.setObjectName("step_time")

        row.addWidget(self.glyph)
        row.addWidget(self.title)
        row.addStretch()
        row.addWidget(self.meta)
        row.addWidget(self.chevron)

        head.mousePressEvent = lambda event: self.toggle()

        self.body = QWidget()

        self._rows_layout = QVBoxLayout(self.body)
        self._rows_layout.setContentsMargins(26, 2, 0, 2)
        self._rows_layout.setSpacing(0)

        outer.addWidget(head)
        outer.addWidget(self.body)

        self.rows = {}
        self.order = []
        self.started = time.monotonic()
        self.done = False

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick)
        self._clock.start(100)

    # ------------------------------------------------

    def _tick(self):

        self.meta.setText(f"{time.monotonic() - self.started:.1f}s")

    def add(self, key, icon, text):

        row = StepRow(icon, text)

        self.rows[key] = row
        self.order.append(row)

        self._rows_layout.addWidget(row)

        self.title.setText("Working…" if not self.done else self.title.text())

        return row

    def finish(self, key, ok, seconds, detail=""):

        row = self.rows.get(key)

        if row is not None:
            row.finish(ok, seconds, detail)

    def complete(self):
        """
        She is finished: stop the spinners and fold the list.
        """

        if self.done:
            return

        self.done = True

        self._clock.stop()

        for row in self.order:

            if not row.finished:
                row.finish(True, -1)

        total = time.monotonic() - self.started
        count = len(self.order)
        failed = sum(1 for r in self.order if not r.ok)

        self.glyph.set_mode("fail" if failed == count and count else "ok")

        if count == 1:
            self.title.setText(self.order[0].label.text())
            self.body.hide()
            self.chevron.hide()

        else:

            self.title.setText(f"Used {count} actions")

            if failed:
                self.title.setText(f"Used {count} actions, {failed} failed")

            # tidy by default; failures stay visible
            self.body.setVisible(bool(failed))
            self.chevron.setText("▴" if failed else "▾")

        self.meta.setText(f"{total:.1f}s")

    def toggle(self):

        if len(self.order) < 2 and self.done:
            return

        show = self.body.isHidden()

        self.body.setVisible(show)
        self.chevron.setText("▴" if show else "▾")


class ConfirmBar(QWidget):
    """
    Yes / No buttons shown under a question from Sophia.
    """

    answered = Signal(str)

    def __init__(self, allow_always=False):

        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        yes = QPushButton("Yes")
        yes.setObjectName("yes")
        yes.clicked.connect(lambda: self.answered.emit("yes"))

        no = QPushButton("No")
        no.setObjectName("no")
        no.clicked.connect(lambda: self.answered.emit("no"))

        layout.addWidget(yes)

        if allow_always:

            always = QPushButton("Always allow")
            always.setToolTip("Stop asking for this kind of action until Sophia restarts")
            always.clicked.connect(lambda: self.answered.emit("always"))

            layout.addWidget(always)

        layout.addWidget(no)
        layout.addStretch()

        self.buttons = (yes, no)


class SuggestionChips(QWidget):
    """
    Tap-to-send ideas shown on the welcome screen.
    """

    chosen = Signal(str)

    COLUMNS = 3

    def __init__(self, suggestions, icons=None):

        super().__init__()

        from PySide6.QtWidgets import QGridLayout

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)

        self.buttons = []

        for i, text in enumerate(suggestions):

            icon = (icons or [""] * len(suggestions))[i]

            button = QPushButton(f"{icon}  {text}" if icon else text)
            button.setObjectName("chip")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, t=text: self.chosen.emit(t))

            layout.addWidget(button, i // self.COLUMNS, i % self.COLUMNS)

            self.buttons.append(button)


class ChatView(QScrollArea):
    """
    Scrolling list of messages.
    """

    def __init__(self):

        super().__init__()

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        body = QWidget()

        self._layout = QVBoxLayout(body)
        self._layout.setContentsMargins(18, 14, 18, 14)
        self._layout.setSpacing(10)
        self._layout.addStretch()

        self.setWidget(body)

        self._rows = []
        self._thinking = None

        # Sophia's mark, drawn beside her messages (set by the window)
        self.avatar_pixmap = None

        # keep the view pinned to the newest message
        self.verticalScrollBar().rangeChanged.connect(self._stick_to_bottom)

    # ------------------------------------------------

    def _stick_to_bottom(self, _min, maximum):

        self.verticalScrollBar().setValue(maximum)

    def _insert(self, widget, align, animate=False):

        row = QWidget()

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        if align == "right":
            layout.addStretch()
            layout.addWidget(widget)

        else:

            layout.setSpacing(10)

            if isinstance(widget, Bubble) and widget.role == "bot":
                layout.addWidget(Avatar(self.avatar_pixmap), 0, Qt.AlignTop)

            elif isinstance(widget, AgentSteps):

                # lines up under her messages
                layout.addSpacing(Avatar.SIZE)

            layout.addWidget(widget)
            layout.addStretch()

        row._content = widget

        widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)

        self._layout.insertWidget(self._layout.count() - 1, row)
        self._rows.append(row)

        self._limit_width(widget)

        if animate:
            fade_in(row)

        return row

    def _limit_width(self, widget):

        limit = max(240, int(self.viewport().width() * BUBBLE_WIDTH_RATIO))

        if isinstance(widget, Bubble):
            widget.fit(limit)

        else:
            widget.setMaximumWidth(limit)

    def resizeEvent(self, event):

        super().resizeEvent(event)

        for row in self._rows:

            widget = getattr(row, "_content", None)

            if isinstance(widget, Bubble):
                self._limit_width(widget)

    # ------------------------------------------------

    def add(self, text, role="bot", animate=False, typing=False):
        """
        Add a message. animate fades it in; typing (bot replies) also
        reveals the text word by word.
        """

        bubble = Bubble("" if typing else text, role)

        self._insert(bubble, "right" if role == "user" else "left", animate)

        if typing:

            bubble.reveal(text)
            bubble.fit(max(240, int(self.viewport().width() * BUBBLE_WIDTH_RATIO)))

        return bubble

    def add_steps(self):
        """
        The live "what I'm doing" card for the current request.
        """

        steps = AgentSteps()

        self._insert(steps, "left", animate=True)

        return steps

    def add_confirm_bar(self, allow_always=False):

        bar = ConfirmBar(allow_always)

        self._insert(bar, "left", animate=True)

        return bar

    def remove_widget(self, widget):

        for row in list(self._rows):

            if widget in row.findChildren(QWidget):

                self._rows.remove(row)
                row.setParent(None)
                row.deleteLater()

    def clear(self):

        for row in self._rows:

            row.setParent(None)
            row.deleteLater()

        self._rows = []
        self._thinking = None

    # ------------------------------------------------

    def show_thinking(self):

        if self._thinking is None:

            bubble = Bubble("", "bot", dots=True)

            self._insert(bubble, "left", animate=True)

            self._thinking = bubble

    def hide_thinking(self):

        if self._thinking is not None:

            self.remove_widget(self._thinking)
            self._thinking = None
