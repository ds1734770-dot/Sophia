import logging
import math
import re

from PySide6.QtCore import (
    QElapsedTimer,
    QObject,
    QRunnable,
    QSize,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
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
from app.ui.car import CarModel, CarWidget, draw_car
from app.ui.characters import CHARACTERS, make_model, valid
from app.ui.activity import describe_step
from app.ui.agents_panel import AgentsPanel
from app.ui.widgets import ChatView, StatusPill, SuggestionChips, collapse, fade_in
from app.voice.wakeword import spoken_name

log = logging.getLogger("sophia.ui")

WELCOME_TITLE = "Hi, I'm Sophia"
WELCOME_SUBTITLE = "Ask me anything, or tell me what to do on your computer."

SUGGESTIONS = [
    "What can you do?",
    "Weather today",
    "Open YouTube",
    "Timer for 10 minutes",
    "How's my computer doing?",
    "Latest news",
]

SUGGESTION_ICONS = ["✨", "⛅", "▶", "⏱", "💻", "📰"]

FRAME_MS = 16
HERO_CAR = (220, 78)
MINI_CAR = (110, 40)
ALERT_SECONDS = 1.6
HISTORY_BUBBLES = 12
MAX_INPUT_LINES = 5

# A finished sentence in streamed text: ends with . ! or ? and a space
SENTENCE_END = re.compile(r"(.+?[.!?])(?:\s+|$)", re.DOTALL)


ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_icon(size):
    """
    The app icon at one size: the yellow car, large, on a dark rounded
    tile. Each size is drawn separately so it stays sharp when small.
    """

    from PySide6.QtCore import QRectF

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#1b1e27"))
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)

    # the car fills the tile (the drawing is wider than the tile and
    # clipped by it); its centre sits slightly low
    width = size * 1.3
    height = width * 170 / 480

    draw_car(
        painter,
        QRectF(-(width - size) / 2 - width * 10 / 480, size * 0.52 - height / 2, width, height),
        CarModel(),
        with_ground=False,
    )

    painter.end()

    return pixmap


def make_icon():
    """
    The app, window and tray icon: the little yellow car.
    """

    icon = QIcon()

    for size in ICON_SIZES:
        icon.addPixmap(render_icon(size))

    return icon


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
        self.setPlaceholderText("Ask Sophia anything, or tell her what to do...")
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

        height = self.fontMetrics().lineSpacing() * lines + 34

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

    # Emitted when the wake word starts a request, before listening
    # begins (the car uses it to come out of hiding)
    wake_activated = Signal()

    # Text of Sophia's answer as Gemini writes it (from a worker thread)
    partial = Signal(str)

    # A tool started or finished (from a worker thread): a dict
    tool_event = Signal(object)

    # An agent reported (from the server thread): kind, task, previous status
    agent_signal = Signal(str, object, object)

    # The user picked an appearance from the menu (car, armor...)
    appearance_requested = Signal(str)

    # For the floating orb: a reply (text, asks a question, offers
    # "always") and short hints such as "I didn't hear anything"
    replied = Signal(str, bool, bool)
    hint = Signal(str)

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
        agent_hub=None,
    ):

        super().__init__()

        self.sophia_factory = sophia_factory
        self.speaker = speaker
        self.recorder_factory = recorder_factory
        self.transcriber = transcriber
        self.settings = settings or QSettings("Sophia", "Sophia")
        self.autostart = autostart or Autostart()
        self.wake_factory = wake_factory
        self.agent_hub = agent_hub
        self._has_car = False
        # no sound by default: the beep would be recorded as speech
        self.beep = beep
        self.wake_listener = None
        self._voice_turn = False

        self.sophia = None
        self.busy = False
        self.recorder = None
        self.confirm_bar = None
        self._stream = None
        self._steps = None
        self._quitting = False

        # the car shown in the chat window; the floating car has its own
        # model and is told what Sophia is doing through these hooks
        self.character = valid(self.settings.value("appearance", "car"))
        self.orb_model = make_model(self.character)
        self.activity_listeners = []     # called with (state, level)
        self.effect_listeners = []       # called with an effect name
        self.hide_on_close = False
        self._alert_until = 0.0
        self._welcome = True
        self._faded_in = False

        self.setWindowTitle("Sophia")
        self.setWindowIcon(make_icon())
        self.resize(760, 780)
        self.setMinimumSize(420, 520)

        self._build()

        self.tray = self._build_tray() if use_tray else None

        self.notified.connect(self._on_notified)
        self.wake_heard.connect(self._on_wake)
        self.partial.connect(self._on_partial)
        self.tool_event.connect(self._on_tool_event)
        self.agent_signal.connect(self._on_agent_signal)

        # animation clock for the orb
        self._clock = QElapsedTimer()
        self._clock.start()

        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._tick)
        self._frame_timer.start(FRAME_MS)

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
        head.setContentsMargins(18, 8, 12, 8)

        # small orb: appears once the welcome screen has collapsed
        self.mini_orb = CarWidget(self.orb_model, *CHARACTERS[self.character]["mini"])
        self.mini_orb.hide()

        title = QLabel("Sophia")
        title.setObjectName("title")

        badge = QLabel("AGENT")
        badge.setObjectName("badge")
        badge.setToolTip("Sophia can act on your computer, with your permission")

        self.status = StatusPill("")

        # her mark beside every message
        self.chat.avatar_pixmap = render_icon(64)

        self.voice_toggle = QPushButton("\U0001F50A")
        self.voice_toggle.setObjectName("icon")
        self.voice_toggle.setCheckable(True)
        self.voice_toggle.setToolTip("Read replies aloud")
        self.voice_toggle.setChecked(
            self.settings.value("voice_replies", False, type=bool)
        )
        self.voice_toggle.toggled.connect(self._on_voice_toggled)

        self._voice_action = None

        menu_button = QPushButton("⋯")
        menu_button.setObjectName("icon")
        menu_button.setToolTip("Menu")
        menu_button.setMenu(self._build_menu())

        head.addWidget(self.mini_orb)
        head.addWidget(title)
        head.addSpacing(6)
        head.addWidget(badge)
        head.addSpacing(12)
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

        # welcome screen: a big orb, a greeting and ideas to tap
        self.hero = QFrame()
        self.hero.setObjectName("hero")

        hero_layout = QVBoxLayout(self.hero)
        hero_layout.setContentsMargins(70, 14, 70, 14)
        hero_layout.setSpacing(6)

        self.hero_orb = CarWidget(self.orb_model, *CHARACTERS[self.character]["hero"])

        hero_title = QLabel(WELCOME_TITLE)
        hero_title.setObjectName("hero_title")
        hero_title.setAlignment(Qt.AlignCenter)

        hero_subtitle = QLabel(WELCOME_SUBTITLE)
        hero_subtitle.setObjectName("hero_subtitle")
        hero_subtitle.setAlignment(Qt.AlignCenter)
        hero_subtitle.setWordWrap(True)

        self.chips = SuggestionChips(SUGGESTIONS, SUGGESTION_ICONS)
        self.chips.chosen.connect(self._on_chip)

        hero_layout.addWidget(self.hero_orb, 0, Qt.AlignHCenter)
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_subtitle)
        hero_layout.addSpacing(8)
        hero_layout.addWidget(self.chips)

        # other agents' tasks (Claude, ChatGPT, Gemini...) when connected
        self.agents_panel = None

        if self.agent_hub is not None:

            self.agents_panel = AgentsPanel(self.agent_hub)
            self.agents_panel.reply.connect(self.reply_to_agent)
            self.agents_panel.dismissed.connect(self._dismiss_agent_task)

            self.agent_hub.listeners.append(
                lambda kind, task, previous: self.agent_signal.emit(kind, task, previous)
            )

        outer.addWidget(header)

        if self.agents_panel is not None:
            outer.addWidget(self.agents_panel)

        outer.addWidget(self.hero)
        outer.addWidget(self.chat, 1)
        outer.addWidget(composer)

        self.setCentralWidget(root)

    def _build_menu(self):

        menu = QMenu(self)

        usage = QAction("AI usage today", self)
        usage.triggered.connect(lambda: self.send("usage", show_user=False))

        looks = menu.addMenu("Appearance")

        for key, info in CHARACTERS.items():

            action = looks.addAction(info["label"])
            action.setCheckable(True)
            action.setChecked(key == self.character)
            action.triggered.connect(lambda _=False, k=key: self.appearance_requested.emit(k))

            looks.aboutToShow.connect(
                lambda a=action, k=key: a.setChecked(k == self.character)
            )

        # without the car window, the chat's menu switches by itself
        self.appearance_requested.connect(
            lambda name: self.set_appearance(name) if not self._has_car else None
        )

        clear = QAction("Clear chat view", self)
        clear.triggered.connect(self.chat.clear)

        self.hands_free_action = QAction("Hands-free (wake word)", self)
        self.hands_free_action.setCheckable(True)
        self.hands_free_action.setEnabled(self.wake_factory is not None)
        self.hands_free_action.setToolTip(
            "Listen for the wake word with the microphone, all on this PC"
        )
        self.hands_free_action.toggled.connect(self._set_hands_free)

        self.screen_confirm_action = QAction("Ask before looking at my screen", self)
        self.screen_confirm_action.setCheckable(True)
        self.screen_confirm_action.setChecked(
            self.settings.value("screen_confirm", False, type=bool)
        )
        self.screen_confirm_action.toggled.connect(self._set_screen_confirm)

        self.autostart_action = QAction("Start with Windows", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self.autostart.is_enabled())
        self.autostart_action.toggled.connect(self.autostart.set_enabled)

        quit_action = QAction("Quit Sophia", self)
        quit_action.triggered.connect(self.quit)

        menu.addAction(usage)
        menu.addAction(clear)
        menu.addAction(self.hands_free_action)
        menu.addAction(self.screen_confirm_action)
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

            # a returning user goes straight to the conversation
            self._leave_welcome(animate=False)

            for message in history:
                self.chat.add(
                    message["content"],
                    "user" if message["role"] == "user" else "bot",
                )

        self._set_ready(True, "Ready")

        self._set_screen_confirm(self.screen_confirm_action.isChecked())

        # live progress: each tool Sophia runs appears as a step
        registry = getattr(getattr(sophia, "brain", None), "registry", None)

        if registry is not None and hasattr(registry, "observers"):
            registry.observers.append(self.tool_event.emit)

        # Remember hands-free across restarts
        # Hands-free is on by default: Sophia answers to her wake word
        # whenever she is running, even with the car hidden
        if self.wake_factory is not None and self.settings.value(
            "hands_free", True, type=bool
        ):
            self.hands_free_action.setChecked(True)

    def _set_screen_confirm(self, on):

        self.settings.setValue("screen_confirm", on)

        brain = getattr(self.sophia, "brain", None)

        if brain is not None and hasattr(brain, "screen_policy"):
            brain.screen_policy["confirm"] = bool(on)

    def _on_start_failed(self, error):

        self._leave_welcome(animate=False)

        self._kick("shake")

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

        self._leave_welcome()

        if show_user:
            self.chat.add(text, "user", animate=True)

        self.busy = True
        self.send_button.setEnabled(False)
        self.status.setText("Thinking...")
        self.chat.show_thinking()

        self._stream = {"bubble": None, "text": "", "spoken": 0}
        self._steps = None

        run_task(
            self.sophia.respond,
            (text, self.partial.emit),
            self._on_reply,
            self._on_reply_failed,
        )

    def _wants_speech(self):

        return self.speaker is not None and (
            self.voice_toggle.isChecked() or self._voice_turn
        )

    def _on_partial(self, piece):
        """
        A piece of the answer arrived: show it at once, and speak each
        sentence as soon as it is finished.
        """

        stream = getattr(self, "_stream", None)

        if stream is None or not self.busy:
            return

        self._complete_steps()

        if stream["bubble"] is None:

            self.chat.hide_thinking()

            stream["bubble"] = self.chat.add("", "bot")

            self.status.setText("Answering...")

        stream["text"] += piece

        stream["bubble"].set_text(stream["text"])
        stream["bubble"].fit(max(240, int(self.chat.viewport().width() * 0.72)))

        if self._wants_speech():

            pending = stream["text"][stream["spoken"]:]

            for match in SENTENCE_END.finditer(pending):

                # the last sentence may still be growing
                if match.end() >= len(pending) and not pending[-1:].isspace():
                    break

                self.speaker.say(match.group(1), interrupt=False)

                stream["spoken"] += match.end()

    def set_appearance(self, name):
        """
        Change how Sophia looks in the header and on the welcome screen.
        """

        name = valid(name)

        self.settings.setValue("appearance", name)

        if name == self.character and self.orb_model.character == name:
            return

        old = self.orb_model

        self.character = name
        self.orb_model = make_model(name)

        self.orb_model.state = old.state
        self.orb_model.attention = old.attention
        self.orb_model.pips = list(old.pips)
        self.orb_model.set_tint(
            old._tint_goal.name() if old._tint_goal is not None else None
        )

        sizes = CHARACTERS[name]

        for widget, size in ((self.mini_orb, sizes["mini"]), (self.hero_orb, sizes["hero"])):

            widget.model = self.orb_model
            widget.setFixedSize(*size)
            widget.update()

    def _on_agent_signal(self, kind, task, previous):

        if self.agents_panel is not None:
            self.agents_panel.refresh()

    def _dismiss_agent_task(self, task_id):

        if self.agent_hub is not None:

            self.agent_hub.dismiss(task_id)

            self.agents_panel.refresh()

    def reply_to_agent(self, task_id, text):
        """
        The user answers an agent's question. If the agent is waiting for
        it (a hook is listening) it receives the answer at once; if not,
        the text is copied so it can be pasted into that agent.
        """

        hub = self.agent_hub

        if hub is None:
            return False

        delivered = hub.is_waiting(task_id)

        hub.answer(task_id, text)

        if not delivered:

            QApplication.clipboard().setText(text)

        row = self.agents_panel.rows.get(task_id) if self.agents_panel else None

        if row is not None:

            row.show_note(
                "Sent to the agent." if delivered
                else "Copied: paste it into the agent's window (it is not listening for replies yet)."
            )

        return delivered

    def _on_tool_event(self, event):
        """
        Show what Sophia is doing as she does it.
        """

        if not self.busy:
            return

        if self._steps is None:

            # the steps card replaces the waiting dots
            self.chat.hide_thinking()

            self._steps = self.chat.add_steps()

            self.status.setText("Working...")

        key = event["token"]

        if event["phase"] == "start":

            icon, text = describe_step(event["name"], event["args"])

            self._steps.add(key, icon, text)

        else:

            self._steps.finish(
                key, event["ok"], event["seconds"],
                "" if event["ok"] else str(event.get("message", ""))[:200],
            )

    def _complete_steps(self):

        if self._steps is not None:

            self._steps.complete()

    def _on_reply(self, result):

        self.chat.hide_thinking()

        self._complete_steps()

        stream = getattr(self, "_stream", None) or {"bubble": None}

        streamed = stream["bubble"] is not None

        if streamed:

            # the final text replaces what was streamed (a tool may have
            # changed the answer)
            stream["bubble"].set_text(result["response"])
            stream["bubble"].fit(max(240, int(self.chat.viewport().width() * 0.72)))

        else:

            self.chat.add(result["response"], "bot", animate=True, typing=True)

        self._maybe_add_confirm_bar()

        pending = self.sophia.pending_actions.current()
        asking = pending is not None and pending.exists()

        self.replied.emit(
            result["response"],
            asking,
            bool(asking and getattr(pending, "data", {}).get("always", False)),
        )

        # a little celebration when Sophia did something for the user
        if result.get("tool_used") and self.confirm_bar is None:
            self._kick("burst")

        elif self.confirm_bar is not None:
            self._kick("bounce")

        # Spoken replies when asked to, and always after a spoken request
        if self._wants_speech():

            said = stream.get("text", "")[:stream.get("spoken", 0)]

            if streamed and said and result["response"].startswith(said):

                # the start was spoken while it streamed: say the rest
                rest = result["response"][len(said):].strip()

                if rest:
                    self.speaker.say(rest, interrupt=False)

            else:
                self.speaker.say(result["response"])

        self._stream = None

        self._voice_turn = False

        self._finish_turn()

    def _on_reply_failed(self, error):

        self.chat.hide_thinking()

        self._complete_steps()

        self.chat.add(f"Something went wrong: {error}", "bot", animate=True)

        self.replied.emit(f"Something went wrong: {error}", False, False)

        self._kick("shake")

        self._voice_turn = False

        self._finish_turn()

    def _finish_turn(self):

        self._steps = None

        self.busy = False
        self.send_button.setEnabled(True)
        self.status.setText(self._idle_status())
        self.input.setFocus()

        self._resume_wake_when_quiet()

    # ------------------------------------------------
    # The living orb
    # ------------------------------------------------

    def _tick(self):

        dt = self._clock.restart() / 1000

        # restart() resets the clock, so keep absolute time ourselves
        self._elapsed = getattr(self, "_elapsed", 0.0) + dt

        state, level = self._orb_state_at(self._elapsed)

        model = self.orb_model

        model.set_state(state)
        model.set_level(level)

        model.step(dt)

        for listener in self.activity_listeners:
            listener(state, level)

        for widget in (self.hero_orb, self.mini_orb):

            if widget.isVisible():
                widget.update()

    def _orb_state_at(self, now):

        if now < self._alert_until:
            return "alert", 0.0

        if self.recorder is not None:
            return "listening", float(getattr(self.recorder, "level", 0.0) or 0.0)

        if self.busy or self.sophia is None:
            return "thinking", 0.0

        speaking = getattr(self.speaker, "speaking", None)

        if speaking is not None and speaking.is_set():

            wave = 0.5 + 0.3 * math.sin(now * 9.0) + 0.2 * math.sin(now * 15.7 + 1.3)

            return "speaking", max(0.15, min(1.0, wave))

        return "idle", 0.0

    def _kick(self, kind):
        """
        A short effect on every car (bounce, burst, shake, honk).
        """

        self.orb_model.kick(kind)

        for listener in self.effect_listeners:
            listener(kind)

    def _on_chip(self, text):

        self.send(text)

    def _leave_welcome(self, animate=True):
        """
        Collapse the welcome screen into the header (the big orb shrinks
        away and the small one fades in).
        """

        if not self._welcome:
            return

        self._welcome = False

        if not animate:

            self.hero.hide()
            self.mini_orb.show()

            return

        def finished():

            self.mini_orb.show()
            fade_in(self.mini_orb, 400)

        collapse(self.hero, 480, on_done=finished)

    def showEvent(self, event):

        super().showEvent(event)

        # a soft entrance the first time the window appears
        if not self._faded_in:

            self._faded_in = True

            from PySide6.QtCore import QPropertyAnimation

            self.setWindowOpacity(0.0)

            animation = QPropertyAnimation(self, b"windowOpacity", self)
            animation.setDuration(380)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.start()

            self._entrance = animation

    # ------------------------------------------------
    # Proactive alerts
    # ------------------------------------------------

    def _on_notified(self, title, text):

        self.chat.add(f"**{title}**\n\n{text}", "bot", animate=True)

        self.replied.emit(f"**{title}**\n\n{text}", False, False)

        self._alert_until = getattr(self, "_elapsed", 0.0) + ALERT_SECONDS
        self._kick("bounce")

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

    def voice_toggle_action(self):
        """
        A menu action ("Spoken replies") kept in step with the toggle
        button, for the floating orb's menu.
        """

        if self._voice_action is None:

            action = QAction("Spoken replies", self)
            action.setCheckable(True)
            action.setChecked(self.voice_toggle.isChecked())

            action.toggled.connect(self.voice_toggle.setChecked)

            self.voice_toggle.toggled.connect(
                lambda on: action.setChecked(on) if action.isChecked() != on else None
            )

            self._voice_action = action

        return self._voice_action

    def start_voice_turn(self):
        """
        Listen for a spoken request (the orb's single click). Clicking
        again while listening stops early; the answer is spoken.
        """

        if self.recorder is not None:

            self.toggle_listening()

            return

        if self.sophia is None:

            self.hint.emit("One moment, I'm still starting up.")

            return

        if self.busy:

            self.hint.emit("Still working on that.")

            return

        if self.recorder_factory is None:

            self.hint.emit("Voice isn't available. Open the chat to type.")

            return

        self._voice_turn = True

        self.toggle_listening()

    def _on_voice_toggled(self, on):

        self.settings.setValue("voice_replies", on)

        if not on and self.speaker is not None:
            self.speaker.stop()

    def toggle_listening(self, preroll=None, skip=None):
        """
        Start (or finish) listening. `preroll` is audio from just before
        now (after a wake word) to keep; `skip` drops the first seconds
        of capture (the start-up chime, when there is one).
        """

        if self.recorder is not None:

            self._finish_listening()

            return

        if self.busy or self.recorder_factory is None:
            return

        if self.speaker is not None:
            self.speaker.stop()

        try:

            self.recorder = self.recorder_factory()

            # tune the recorder to the room and to how it was started
            if self.wake_listener is not None and hasattr(self.recorder, "noise_floor"):
                self.recorder.noise_floor = self.wake_listener.noise_floor

            if hasattr(self.recorder, "skip_seconds"):

                if skip is None:

                    # a button press plays a chime that the mic would hear
                    skip = 0.0 if preroll is not None else 0.35

                self.recorder.skip_seconds = skip

            if preroll is not None:
                self.recorder.start(preroll=preroll)

            else:
                self.recorder.start()

        except Exception as e:

            log.exception("Microphone unavailable")

            self.recorder = None
            self._voice_turn = False
            self.chat.add(f"I couldn't use the microphone: {e}", "bot")

            self.hint.emit(f"I couldn't use the microphone: {e}")

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

            self.hint.emit("I didn't hear anything. Click and try again.")

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

            self.hint.emit("I didn't catch that. Click and try again.")

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

        self.hint.emit(f"I couldn't start the wake word: {error}")

    def _on_wake(self):

        # Heard the wake word: listen for the request
        if self.wake_listener is None or self.busy or self.recorder is not None:
            return

        listener = self.wake_listener

        # what was said right after the wake word, so no words are lost
        preroll = None

        if getattr(listener, "last_wake_time", None) is not None and hasattr(listener, "audio_since"):
            preroll = listener.audio_since(listener.last_wake_time - 0.1)

        listener.pause()

        if self.speaker is not None:
            self.speaker.stop()

        self.wake_activated.emit()

        if self.beep is not None:
            self.beep()

        self._voice_turn = True

        self.toggle_listening(preroll=preroll if preroll is not None and len(preroll) else None, skip=0.0)

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

        # Closing the window keeps Sophia in the tray (or as the floating
        # orb) so she stays available; Quit in the menu really exits.
        if (self.tray is not None or self.hide_on_close) and not self._quitting:

            event.ignore()
            self.hide()

            return

        super().closeEvent(event)
