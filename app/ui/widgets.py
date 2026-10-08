from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

BUBBLE_WIDTH_RATIO = 0.78


class Bubble(QFrame):
    """
    One chat message. role: "user", "bot" or "note".
    """

    def __init__(self, text, role="bot"):

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

        self.set_text(text)

    def set_text(self, text):

        self.label.setText(text)

    def text(self):

        return self.label.text()

    def fit(self, max_width):
        """
        Size the bubble to its text, up to max_width. (A word-wrapped
        label on its own would collapse to a narrow column.)
        """

        metrics = self.label.fontMetrics()

        widest = max(
            (metrics.horizontalAdvance(line) for line in self.label.text().split("\n")),
            default=0,
        )

        # padding, plus room for list bullets and bold text
        wanted = widest + 28 + 36

        self.setFixedWidth(max(60, min(max_width, wanted)))


class ConfirmBar(QWidget):
    """
    Yes / No buttons shown under a question from Sophia.
    """

    answered = Signal(str)

    def __init__(self):

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
        layout.addWidget(no)
        layout.addStretch()

        self.buttons = (yes, no)


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
        self._dots = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)

        # keep the view pinned to the newest message
        self.verticalScrollBar().rangeChanged.connect(self._stick_to_bottom)

    # ------------------------------------------------

    def _stick_to_bottom(self, _min, maximum):

        self.verticalScrollBar().setValue(maximum)

    def _insert(self, widget, align):

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

    def add(self, text, role="bot"):

        bubble = Bubble(text, role)

        self._insert(bubble, "right" if role == "user" else "left")

        return bubble

    def add_confirm_bar(self):

        bar = ConfirmBar()

        self._insert(bar, "left")

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

            self._thinking = self.add("...", "bot")
            self._dots = 0
            self._timer.start(350)

    def hide_thinking(self):

        self._timer.stop()

        if self._thinking is not None:

            self.remove_widget(self._thinking)
            self._thinking = None

    def _animate(self):

        self._dots = (self._dots + 1) % 4

        if self._thinking is not None:
            self._thinking.set_text("." * max(1, self._dots))
