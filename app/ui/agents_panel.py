"""
The agents strip at the top of the chat window: one card per task that
Claude, ChatGPT, Gemini or another agent has reported, in that agent's
colour, with a live status. A task that needs the user gets a pulsing
"Needs you" chip and a box to reply from here.
"""

import math
import re
import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

MAX_ROWS = 4
KEEP_FINISHED_SECONDS = 120

STATUS_TEXT = {
    "running": "Working",
    "needs_input": "Needs you",
    "done": "Done",
    "failed": "Failed",
}

YES_NO_START = re.compile(
    r"^(should|shall|do|does|did|can|could|would|will|is|are|want|may|ok(ay)?)\b",
    re.IGNORECASE,
)


def is_yes_no(question):
    """
    Is this a question the user can answer with yes or no?
    """

    text = (question or "").strip().rstrip("?").strip()

    # the last sentence of the question is the one being asked
    last = re.split(r"(?<=[.!?])\s+", text)[-1] if text else ""

    return bool(YES_NO_START.match(last)) and " or " not in last.lower()


def clock_text(seconds):

    seconds = int(seconds)

    if seconds < 60:
        return f"{seconds}s"

    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"

    return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m"


class AgentRow(QFrame):

    reply = Signal(str, str)         # task id, text
    dismissed = Signal(str)

    def __init__(self, task):

        super().__init__()

        self.setObjectName("agent_row")

        self.task_id = task.id
        self.color = task.color
        self.status = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 10, 8)
        outer.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(10)

        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {task.color}; background: transparent; font-size: 12px;")

        self.name = QLabel(task.label)
        self.name.setObjectName("agent_name")
        self.name.setStyleSheet(f"color: {task.color}; background: transparent;")

        self.title = QLabel("")
        self.title.setObjectName("agent_title")

        self.chip = QLabel("")
        self.chip.setObjectName("agent_chip")

        self.time = QLabel("")
        self.time.setObjectName("step_time")

        self.close = QPushButton("✕")
        self.close.setObjectName("agent_close")
        self.close.setFixedSize(22, 22)
        self.close.setCursor(Qt.PointingHandCursor)
        self.close.setToolTip("Dismiss")
        self.close.clicked.connect(lambda: self.dismissed.emit(self.task_id))

        top.addWidget(self.dot)
        top.addWidget(self.name)
        top.addWidget(self.title, 1)
        top.addWidget(self.chip)
        top.addWidget(self.time)
        top.addWidget(self.close)

        outer.addLayout(top)

        # the question and a place to answer it
        self.ask = QWidget()
        self.ask.setObjectName("agent_ask")

        ask = QVBoxLayout(self.ask)
        ask.setContentsMargins(22, 0, 0, 0)
        ask.setSpacing(6)

        self.question = QLabel("")
        self.question.setObjectName("agent_question")
        self.question.setWordWrap(True)

        answer_row = QHBoxLayout()
        answer_row.setSpacing(6)

        self.yes = QPushButton("Yes")
        self.yes.setObjectName("yes")
        self.yes.clicked.connect(lambda: self._send("yes"))

        self.no = QPushButton("No")
        self.no.setObjectName("no")
        self.no.clicked.connect(lambda: self._send("no"))

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Reply to this agent...")
        self.edit.returnPressed.connect(lambda: self._send(self.edit.text()))

        self.send = QPushButton("Reply")
        self.send.setObjectName("send")
        self.send.clicked.connect(lambda: self._send(self.edit.text()))

        self.note = QLabel("")
        self.note.setObjectName("step_time")

        answer_row.addWidget(self.yes)
        answer_row.addWidget(self.no)
        answer_row.addWidget(self.edit, 1)
        answer_row.addWidget(self.send)

        ask.addWidget(self.question)
        ask.addLayout(answer_row)
        ask.addWidget(self.note)

        outer.addWidget(self.ask)

        self.ask.hide()

        self._pulse = 0.0

        self.refresh(task)

    # ------------------------------------------------

    def _send(self, text):

        text = (text or "").strip()

        if not text:
            return

        self.edit.clear()

        self.reply.emit(self.task_id, text)

    def show_note(self, text):

        self.note.setText(text)

    def refresh(self, task, now=None):

        now = now or time.time()

        changed = task.status != self.status

        self.status = task.status

        self.title.setText(task.title or task.project or "")
        self.title.setToolTip(task.title)

        self.chip.setText(STATUS_TEXT.get(task.status, task.status))
        self.chip.setProperty("status", task.status)

        if changed:

            self.chip.style().unpolish(self.chip)
            self.chip.style().polish(self.chip)

        self.time.setText(
            clock_text(task.elapsed(now)) if task.status in ("running", "needs_input")
            else clock_text(max(0, task.updated - task.started))
        )

        asking = task.status == "needs_input"

        self.ask.setVisible(asking)

        if asking:

            self.question.setText(task.question or "This agent needs your input.")

            yes_no = is_yes_no(task.question)

            self.yes.setVisible(yes_no)
            self.no.setVisible(yes_no)

        self.close.setVisible(task.status in ("done", "failed"))

        self.setStyleSheet(
            f"QFrame#agent_row {{ border-left: 3px solid {task.color}; }}"
        )

    def pulse(self, step):
        """
        The "Needs you" chip breathes to catch the eye.
        """

        if self.status != "needs_input":
            return

        self._pulse += step

        glow = (1 + math.sin(self._pulse)) / 2

        color = QColor(self.color)
        color.setAlpha(int(40 + 90 * glow))

        self.chip.setStyleSheet(
            f"background: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});"
            f"color: white; border-radius: 9px; padding: 1px 8px;"
        )


class AgentsPanel(QFrame):

    reply = Signal(str, str)
    dismissed = Signal(str)

    def __init__(self, hub):

        super().__init__()

        self.setObjectName("agents")

        self.hub = hub
        self.rows = {}

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 8, 14, 8)
        self._layout.setSpacing(6)

        self.more = QLabel("")
        self.more.setObjectName("step_time")

        self._layout.addWidget(self.more)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(250)

        self.hide()

    # ------------------------------------------------

    def visible_tasks(self, now=None):

        now = now or time.time()

        tasks = [
            t for t in self.hub.all()
            if t.status in ("running", "needs_input")
            or now - t.updated < KEEP_FINISHED_SECONDS
        ]

        order = {"needs_input": 0, "running": 1, "failed": 2, "done": 3}

        tasks.sort(key=lambda t: (order[t.status], -t.updated))

        return tasks

    def refresh(self):

        tasks = self.visible_tasks()

        shown = tasks[:MAX_ROWS]
        ids = {t.id for t in shown}

        for task_id in list(self.rows):

            if task_id not in ids:

                row = self.rows.pop(task_id)
                row.setParent(None)
                row.deleteLater()

        for index, task in enumerate(shown):

            row = self.rows.get(task.id)

            if row is None:

                row = AgentRow(task)
                row.reply.connect(self.reply)
                row.dismissed.connect(self.dismissed)

                self.rows[task.id] = row

            else:
                row.refresh(task)

            self._layout.insertWidget(index, row)

        extra = len(tasks) - len(shown)

        self.more.setText(f"+{extra} more" if extra > 0 else "")
        self.more.setVisible(extra > 0)

        self.setVisible(bool(shown))

    def _tick(self):

        if not self.rows:
            return

        now = time.time()

        visible = self.visible_tasks(now)

        # a finished card has timed out (or one arrived): rebuild the list
        if {t.id for t in visible[:MAX_ROWS]} != set(self.rows):
            self.refresh()

        for task in visible:

            row = self.rows.get(task.id)

            if row is not None:

                row.time.setText(
                    clock_text(task.elapsed(now)) if task.status in ("running", "needs_input")
                    else clock_text(max(0, task.updated - task.started))
                )

                row.pulse(0.35)
