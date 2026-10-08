import logging

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QSize,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.computer.autostart import Autostart
from app.ui import theme
from app.ui.widgets import ChatView
from app.voice.wakeword import spoken_name

log = logging.getLogger("sophia.ui")

GREETING = "Hi, I'm Sophia. Ask me anything, or tell me what to do on your computer."
HISTORY_BUBBLES = 12
MAX_INPUT_LINES = 5


def make_icon():
    """
    The app icon, drawn in code so no image file is needed.
    """

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(theme.ACCENT))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 60, 60)
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Segoe UI", 30, QFont.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "S")
    painter.end()

    return QIcon(pixmap)


def _default_beep():
    """
    A short tone: Sophia heard the wake word and is listening.
    """

    try:

        import winsound

        winsound.Beep(880, 120)

    except Exception:
        pass


def make_mic_icon(color="#e8eaf0"):
    """
    A microphone glyph drawn in code (the emoji renders inconsistently).
    """

    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPen

    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    pen = QPen(QColor(color))
    pen.setWidthF(3.2)
    pen.setCapStyle(Qt.RoundCap)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(QRectF(17, 5, 14, 24), 7, 7)

    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawArc(QRectF(11, 14, 26, 22), 180 * 16, 180 * 16)
    painter.drawLine(24, 36, 24, 43)
    painter.drawLine(17, 43, 31, 43)

    painter.end()

    return QIcon(pixmap)


# ---------------------------------------------------------------
# Background work
# ---------------------------------------------------------------

class _Signals(QObject):

    done = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    """
    Runs a function off the UI thread and reports back by signal.
    """

    def __init__(self, function, *args):

        super().__init__()

        self.function = function
        self.args = args
        self.signals = _Signals()

    def run(self):

        try:
            result = self.function(*self.args)

        except Exception as e:

            log.exception("Background task failed")
            self.signals.failed.emit(str(e))

            return

        self.signals.done.emit(result)


def run_task(function, args, on_done, on_failed):

    task = Task(function, *args)

    task.signals.done.connect(on_done)
    task.signals.failed.connect(on_failed)

    QThreadPool.globalInstance().start(task)

    return task


# ---------------------------------------------------------------
# Input box
# ---------------------------------------------------------------

class InputBox(QPlainTextEdit):
    """
    Enter sends, Shift+Enter adds a line. Grows up to a few lines.
    """

    submitted = Signal()

    def __init__(self):

        super().__init__()

        self.setObjectName("input")
        self.setPlaceholderText("Message Sophia...")
        self.textChanged.connect(self._resize)

        self._resize()

    def keyPressEvent(self, event):

        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (
            event.modifiers() & Qt.ShiftModifier
        ):

            self.submitted.emit()

            return

        super().keyPressEvent(event)

    def _resize(self):

        lines = min(MAX_INPUT_LINES, max(1, self.document().blockCount()))

        height = self.fontMetrics().lineSpacing() * lines + 22

        self.setFixedHeight(height)


# ---------------------------------------------------------------
# Main window
# ---------------------------------------------------------------

class MainWindow(QMainWindow):

    # Reminders arrive on a background thread; the signal moves them
    # to the UI thread.
    notified = Signal(str, str)

    # The wake word is heard on the audio thread
    wake_heard = Signal()

    def __init__(
        self,
        sophia_factory,
        speaker=None,
        recorder_factory=None,
        transcriber=None,
        settings=None,
        use_tray=True,
        autostart=None,
        wake_factory=None,
        beep=None,
    ):

        super().__init__()

        self.sophia_factory = sophia_factory
        self.speaker = speaker
        self.recorder_factory = recorder_factory
        self.transcriber = transcriber
        self.settings = settings or QSettings("Sophia", "Sophia")
        self.autostart = autostart or Autostart()
        self.wake_factory = wake_factory
        self.beep = beep or _default_beep
        self.wake_listener = None
        self._voice_turn = False

        self.sophia = None
        self.busy = False
        self.recorder = None
        self.confirm_bar = None
        self._quitting = False

        self.setWindowTitle("Sophia")
        self.setWindowIcon(make_icon())
        self.resize(760, 780)
        self.setMinimumSize(420, 520)

        self._build()

        self.tray = self._build_tray() if use_tray else None

        self.notified.connect(self._on_notified)
        self.wake_heard.connect(self._on_wake)

        self._set_ready(False, "Starting...")

        run_task(self.sophia_factory, (), self._on_started, self._on_start_failed)

    # ------------------------------------------------
    # Layout
    # ------------------------------------------------

    def _build(self):

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.chat = ChatView()

        # header
        header = QFrame()
        header.setObjectName("header")

        head = QHBoxLayout(header)
        head.setContentsMargins(18, 12, 12, 12)

        title = QLabel("Sophia")
        title.setObjectName("title")

        self.status = QLabel("")
        self.status.setObjectName("status")

        self.voice_toggle = QPushButton("\U0001F50A")
        self.voice_toggle.setObjectName("icon")
        self.voice_toggle.setCheckable(True)
        self.voice_toggle.setToolTip("Read replies aloud")
        self.voice_toggle.setChecked(
            self.settings.value("voice_replies", False, type=bool)
        )
        self.voice_toggle.toggled.connect(self._on_voice_toggled)

        menu_button = QPushButton("⋯")
        menu_button.setObjectName("icon")
        menu_button.setToolTip("Menu")
        menu_button.setMenu(self._build_menu())

        head.addWidget(title)
        head.addSpacing(10)
        head.addWidget(self.status)
        head.addStretch()
        head.addWidget(self.voice_toggle)
        head.addWidget(menu_button)

        # composer
        composer = QFrame()
        composer.setObjectName("composer")

        row = QHBoxLayout(composer)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(8)

        self.input = InputBox()
        self.input.submitted.connect(self.send_from_input)

        self.mic = QPushButton()
        self.mic.setIcon(make_mic_icon())
        self.mic.setIconSize(QSize(20, 20))
        self.mic.setObjectName("mic")
        self.mic.setProperty("listening", False)
        self.mic.setToolTip("Speak to Sophia")
        self.mic.clicked.connect(self.toggle_listening)

        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("send")
        self.send_button.clicked.connect(self.send_from_input)

        row.addWidget(self.input, 1)
        row.addWidget(self.mic, 0, Qt.AlignBottom)
        row.addWidget(self.send_button, 0, Qt.AlignBottom)

        outer.addWidget(header)
        outer.addWidget(self.chat, 1)
        outer.addWidget(composer)

        self.setCentralWidget(root)

    def _build_menu(self):

        menu = QMenu(self)

        usage = QAction("AI usage today", self)
        usage.triggered.connect(lambda: self.send("usage", show_user=False))

        clear = QAction("Clear chat view", self)
        clear.triggered.connect(self.chat.clear)

        self.hands_free_action = QAction("Hands-free (wake word)", self)
        self.hands_free_action.setCheckable(True)
        self.hands_free_action.setEnabled(self.wake_factory is not None)
        self.hands_free_action.setToolTip(
            "Listen for the wake word with the microphone, all on this PC"
        )
        self.hands_free_action.toggled.connect(self._set_hands_free)

        self.autostart_action = QAction("Start with Windows", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self.autostart.is_enabled())
        self.autostart_action.toggled.connect(self.autostart.set_enabled)

        quit_action = QAction("Quit Sophia", self)
        quit_action.triggered.connect(self.quit)

        menu.addAction(usage)
        menu.addAction(clear)
        menu.addAction(self.hands_free_action)
        menu.addAction(self.autostart_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        return menu

    def _build_tray(self):

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None

        tray = QSystemTrayIcon(make_icon(), self)
        tray.setToolTip("Sophia (Ctrl+Alt+Space)")

        menu = QMenu()

        show = QAction("Open Sophia", self)
        show.triggered.connect(self.bring_to_front)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit)

        menu.addAction(show)
        menu.addAction(quit_action)

        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: self.bring_to_front()
            if reason == QSystemTrayIcon.Trigger
            else None
        )

        tray.show()

        self._tray_menu = menu

        return tray

    # ------------------------------------------------
    # State
    # ------------------------------------------------

    def _set_ready(self, ready, status=""):

        self.input.setEnabled(ready)
        self.send_button.setEnabled(ready)
        self.mic.setEnabled(ready and self.recorder_factory is not None)
        self.status.setText(status)

        if ready:
            self.input.setFocus()

    def _on_started(self, sophia):

        self.sophia = sophia

        if hasattr(sophia, "set_notifier"):
            sophia.set_notifier(lambda title, text: self.notified.emit(title, text))

        try:
            sophia.start_services()

        except Exception:
            log.exception("Background services failed to start")

        history = [
            m for m in sophia.memory.get_history()
            if m["role"] in ("user", "assistant")
        ][-HISTORY_BUBBLES:]

        if history:

            for message in history:
                self.chat.add(
                    message["content"],
                    "user" if message["role"] == "user" else "bot",
                )

        else:

            self.chat.add(GREETING)

        self._set_ready(True, "Ready")

        # Remember hands-free across restarts
        if self.wake_factory is not None and self.settings.value(
            "hands_free", False, type=bool
        ):
            self.hands_free_action.setChecked(True)

    def _on_start_failed(self, error):

        self.chat.add(
            f"Sophia could not start: {error}\n\nSee data/logs/sophia.log.",
            "bot",
        )

        self.status.setText("Not running")

    # ------------------------------------------------
    # Sending and receiving
    # ------------------------------------------------

    def send_from_input(self):

        text = self.input.toPlainText().strip()

        if not text:
            return

        self.input.clear()

        self.send(text)

    def send(self, text, show_user=True):

        if self.sophia is None or self.busy:
            return

        self._drop_confirm_bar()

        if self.speaker is not None:
            self.speaker.stop()

        if show_user:
            self.chat.add(text, "user")

        self.busy = True
        self.send_button.setEnabled(False)
        self.status.setText("Thinking...")
        self.chat.show_thinking()

        run_task(self.sophia.respond, (text,), self._on_reply, self._on_reply_failed)

    def _on_reply(self, result):

        self.chat.hide_thinking()

        self.chat.add(result["response"], "bot")

        self._maybe_add_confirm_bar()

        # Spoken replies when asked to, and always after a spoken request
        if self.speaker is not None and (
            self.voice_toggle.isChecked() or self._voice_turn
        ):
            self.speaker.say(result["response"])

        self._voice_turn = False

        self._finish_turn()

    def _on_reply_failed(self, error):

        self.chat.hide_thinking()

        self.chat.add(f"Something went wrong: {error}", "bot")

        self._voice_turn = False

        self._finish_turn()

    def _finish_turn(self):

        self.busy = False
        self.send_button.setEnabled(True)
        self.status.setText(self._idle_status())
        self.input.setFocus()

        self._resume_wake_when_quiet()

    # ------------------------------------------------
    # Proactive alerts
    # ------------------------------------------------

    def _on_notified(self, title, text):

        self.chat.add(f"**{title}**\n\n{text}", "bot")

        if self.tray is not None:
            self.tray.showMessage(title, text, QSystemTrayIcon.Information, 10000)

        if self.speaker is not None and self.voice_toggle.isChecked():
            self.speaker.say(f"{title}. {text}", interrupt=False)

        QApplication.alert(self)

    # ------------------------------------------------
    # Confirmations
    # ------------------------------------------------

    def _maybe_add_confirm_bar(self):

        pending = self.sophia.pending_actions.current()

        if pending is None or not pending.exists():
            return

        bar = self.chat.add_confirm_bar(
            allow_always=getattr(pending, "data", {}).get("always", False)
        )

        bar.answered.connect(self._on_confirm_answer)

        self.confirm_bar = bar

    def _on_confirm_answer(self, answer):

        self.send(answer)

    def _drop_confirm_bar(self):

        if self.confirm_bar is not None:

            self.chat.remove_widget(self.confirm_bar)
            self.confirm_bar = None

    # ------------------------------------------------
    # Voice
    # ------------------------------------------------

    def _on_voice_toggled(self, on):

        self.settings.setValue("voice_replies", on)

        if not on and self.speaker is not None:
            self.speaker.stop()

    def toggle_listening(self):

        if self.recorder is not None:

            self._finish_listening()

            return

        if self.busy or self.recorder_factory is None:
            return

        if self.speaker is not None:
            self.speaker.stop()

        try:

            self.recorder = self.recorder_factory()
            self.recorder.start()

        except Exception as e:

            log.exception("Microphone unavailable")

            self.recorder = None
            self._voice_turn = False
            self.chat.add(f"I couldn't use the microphone: {e}", "bot")

            self._resume_wake_when_quiet()

            return

        self._set_listening(True)
        self.status.setText("Listening...")

        self._poll = QTimer(self)
        self._poll.timeout.connect(self._check_recorder)
        self._poll.start(100)

    def _set_listening(self, listening):

        self.mic.setProperty("listening", listening)
        self.mic.style().unpolish(self.mic)
        self.mic.style().polish(self.mic)

    def _check_recorder(self):

        if self.recorder is not None and self.recorder.finished.is_set():

            self._finish_listening()

    def _finish_listening(self):

        self._poll.stop()

        audio = self.recorder.stop()

        self.recorder = None

        self._set_listening(False)

        if len(audio) == 0:

            self.status.setText("I didn't hear anything")

            self._voice_turn = False
            self._resume_wake_when_quiet()

            return

        self.status.setText("Transcribing (first time loads the speech model)...")

        run_task(
            self.transcriber.transcribe,
            (audio,),
            self._on_transcribed,
            self._on_transcribe_failed,
        )

    def _on_transcribed(self, text):

        if not text:

            self.status.setText("I didn't catch that")

            self._voice_turn = False
            self._resume_wake_when_quiet()

            return

        self.status.setText("Ready")

        self.send(text)

    def _on_transcribe_failed(self, error):

        self.status.setText("Ready")

        self.chat.add(f"I couldn't understand the audio: {error}", "bot")

        self._voice_turn = False
        self._resume_wake_when_quiet()

    # ------------------------------------------------
    # Hands-free (wake word)
    # ------------------------------------------------

    def _idle_status(self):

        if self.wake_listener is not None and self.wake_listener.running:
            return f"Listening for '{spoken_name(self.wake_listener.word)}'"

        return "Ready"

    def _set_hands_free(self, on):

        self.settings.setValue("hands_free", on)

        if not on:

            if self.wake_listener is not None:

                self.wake_listener.stop()
                self.wake_listener = None

            self.status.setText(self._idle_status())

            return

        if self.wake_factory is None or self.wake_listener is not None:
            return

        listener = self.wake_factory(self.wake_heard.emit)

        self.wake_listener = listener

        self.status.setText("Starting wake word (first time downloads a small model)...")

        run_task(listener.start, (), self._on_wake_ready, self._on_wake_failed)

    def _on_wake_ready(self, _result):

        self.status.setText(self._idle_status())

    def _on_wake_failed(self, error):

        self.wake_listener = None

        self.hands_free_action.blockSignals(True)
        self.hands_free_action.setChecked(False)
        self.hands_free_action.blockSignals(False)

        self.settings.setValue("hands_free", False)

        self.status.setText("Ready")

        self.chat.add(f"I couldn't start the wake word: {error}", "bot")

    def _on_wake(self):

        # Heard the wake word: listen for the request
        if self.wake_listener is None or self.busy or self.recorder is not None:
            return

        self.wake_listener.pause()

        if self.speaker is not None:
            self.speaker.stop()

        self.beep()

        self._voice_turn = True

        self.toggle_listening()

    def _resume_wake_when_quiet(self, tries=0):
        """
        Listen for the wake word again once Sophia has finished
        speaking (so she does not hear herself).
        """

        if self.wake_listener is None or not self.wake_listener.running:
            return

        if self.busy or self.recorder is not None:
            return

        speaking = self.speaker is not None and self.speaker.speaking.is_set()

        if speaking and tries < 120:

            QTimer.singleShot(500, lambda: self._resume_wake_when_quiet(tries + 1))

            return

        self.wake_listener.resume()
        self.status.setText(self._idle_status())

    # ------------------------------------------------
    # Window behaviour
    # ------------------------------------------------

    def bring_to_front(self):

        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def toggle_visibility(self):

        if self.isVisible() and self.isActiveWindow():
            self.hide()

        else:
            self.bring_to_front()

    def quit(self):

        self._quitting = True

        if self.wake_listener is not None:
            self.wake_listener.stop()

        if self.speaker is not None:
            self.speaker.close()

        if self.tray is not None:
            self.tray.hide()

        QApplication.quit()

    def closeEvent(self, event):

        # Closing the window keeps Sophia in the tray so the hotkey
        # still works; Quit in the menu really exits.
        if self.tray is not None and not self._quitting:

            event.ignore()
            self.hide()

            return

        super().closeEvent(event)
