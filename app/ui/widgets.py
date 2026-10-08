import math
import re

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
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

        if dots:

            self.dots = ThinkingDots()
            layout.addWidget(self.dots)
            self.label.hide()

        else:

            self.set_text(text)

    # ------------------------------------------------

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

    def __init__(self, suggestions):

        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addStretch()

        self.buttons = []

        for text in suggestions:

            button = QPushButton(text)
            button.setObjectName("chip")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, t=text: self.chosen.emit(t))

            layout.addWidget(button)

            self.buttons.append(button)

        layout.addStretch()


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
            layout.addWidget(widget)
            layout.addStretch()

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

            widget = row.layout().itemAt(0).widget() or row.layout().itemAt(1).widget()

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
