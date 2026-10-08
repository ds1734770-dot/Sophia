import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.widgets import Bubble, ConfirmBar


@pytest.fixture(scope="session")
def qapp():

    return QApplication.instance() or QApplication([])


def pump(qapp, condition, seconds=3):

    deadline = time.time() + seconds

    while time.time() < deadline:

        qapp.processEvents()

        if condition():
            return True

        time.sleep(0.01)

    return False


class FakePending:

    def __init__(self):
        self.active = False

    def exists(self):
        return self.active


class FakeSophia:

    def __init__(self, history=None, replies=None):

        self.memory = SimpleNamespace(get_history=lambda: history or [])
        self.pending = FakePending()
        self.pending_actions = SimpleNamespace(current=lambda: self.pending)
        self.replies = replies or {}
        self.received = []
        self.started = False

    def start_services(self):
        self.started = True

    def respond(self, text, on_text=None):

        self.received.append(text)

        reply = self.replies.get(text, "ok")

        if isinstance(reply, Exception):
            raise reply

        if text == "close notepad":
            self.pending.active = True
            return {"response": "Reply 'yes' to confirm", "tool_used": True}

        self.pending.active = False

        return {"response": reply, "tool_used": False}


class FakeSpeaker:

    def __init__(self):
        self.said = []
        self.stopped = 0
        self.closed = False

    def say(self, text, interrupt=True):
        self.said.append(text)

    def stop(self):
        self.stopped += 1

    def close(self):
        self.closed = True


class FakeRecorder:

    def __init__(self, audio):
        self.audio = audio
        self.finished = threading.Event()
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        return self.audio


class FakeTranscriber:

    def __init__(self, text):
        self.text = text

    def transcribe(self, audio):
        return self.text


class FakeAutostart:

    def __init__(self):
        self.enabled = False

    def is_enabled(self):
        return self.enabled

    def set_enabled(self, value):
        self.enabled = value


def make_window(qapp, sophia=None, **kwargs):

    sophia = sophia or FakeSophia()

    window = MainWindow(
        lambda: sophia,
        settings=QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat),
        use_tray=False,
        autostart=FakeAutostart(),
        **kwargs,
    )

    assert pump(qapp, lambda: window.sophia is not None)

    return window, sophia


def bubbles(window):

    return [
        (b.role, b.text())
        for b in window.chat.widget().findChildren(Bubble)
    ]


def test_starts_with_a_greeting_and_starts_services(qapp):

    window, sophia = make_window(qapp)

    assert sophia.started
    assert window.send_button.isEnabled()

    # a new user sees the welcome screen, not an empty chat
    assert not window.hero.isHidden()
    assert bubbles(window) == []


def test_recent_history_is_shown(qapp):

    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "system", "content": "hidden"},
    ]

    window, _ = make_window(qapp, FakeSophia(history))

    assert bubbles(window) == [("user", "hi"), ("bot", "hello")]


def test_sending_a_message_shows_the_reply(qapp):

    window, sophia = make_window(qapp, FakeSophia(replies={"hello": "hi there"}))

    window.input.setPlainText("hello")
    window.send_from_input()

    assert window.busy
    assert not window.send_button.isEnabled()

    assert pump(qapp, lambda: not window.busy)

    assert sophia.received == ["hello"]
    assert ("user", "hello") in bubbles(window)
    assert ("bot", "hi there") in bubbles(window)
    assert window.input.toPlainText() == ""
    assert window.send_button.isEnabled()


def test_blank_messages_are_ignored(qapp):

    window, sophia = make_window(qapp)

    window.input.setPlainText("   ")
    window.send_from_input()

    assert sophia.received == []


def test_a_second_message_while_busy_is_ignored(qapp):

    window, sophia = make_window(qapp)

    window.send("one")
    window.send("two")

    assert pump(qapp, lambda: not window.busy)
    assert sophia.received == ["one"]


def test_errors_are_shown_not_raised(qapp):

    window, _ = make_window(qapp, FakeSophia(replies={"boom": RuntimeError("bad")}))

    window.send("boom")

    assert pump(qapp, lambda: not window.busy)
    assert any("Something went wrong: bad" in t for _, t in bubbles(window))


def test_confirmation_buttons_answer_for_the_user(qapp):

    window, sophia = make_window(qapp)

    window.send("close notepad")
    assert pump(qapp, lambda: not window.busy)

    bar = window.chat.widget().findChildren(ConfirmBar)
    assert len(bar) == 1

    bar[0].buttons[0].click()   # Yes

    assert pump(qapp, lambda: sophia.received == ["close notepad", "yes"] and not window.busy)

    # the buttons are gone once answered
    assert pump(qapp, lambda: not window.chat.widget().findChildren(ConfirmBar))


def test_replies_are_spoken_only_when_voice_is_on(qapp):

    speaker = FakeSpeaker()
    window, _ = make_window(qapp, FakeSophia(replies={"a": "first", "b": "second"}), speaker=speaker)

    window.send("a")
    assert pump(qapp, lambda: not window.busy)
    assert speaker.said == []

    window.voice_toggle.setChecked(True)

    window.send("b")
    assert pump(qapp, lambda: not window.busy)
    assert speaker.said == ["second"]


def test_voice_input_is_transcribed_and_sent(qapp):

    audio = np.ones(16000, dtype="float32")
    recorder = FakeRecorder(audio)

    window, sophia = make_window(
        qapp,
        recorder_factory=lambda: recorder,
        transcriber=FakeTranscriber("open notepad"),
        speaker=FakeSpeaker(),
    )

    assert window.mic.isEnabled()

    window.toggle_listening()
    assert recorder.started
    assert window.recorder is recorder

    recorder.finished.set()

    assert pump(qapp, lambda: sophia.received == ["open notepad"])
    assert window.recorder is None


def test_silence_sends_nothing(qapp):

    recorder = FakeRecorder(np.zeros(0, dtype="float32"))

    window, sophia = make_window(
        qapp, recorder_factory=lambda: recorder, transcriber=FakeTranscriber("x")
    )

    window.toggle_listening()
    window.toggle_listening()    # stop early

    assert sophia.received == []
    assert "didn't hear" in window.status.text()


def test_unavailable_microphone_is_reported(qapp):

    def broken():
        raise OSError("no microphone")

    window, _ = make_window(qapp, recorder_factory=broken, transcriber=FakeTranscriber("x"))

    window.toggle_listening()

    assert window.recorder is None
    assert any("microphone" in t for _, t in bubbles(window))


def test_mic_is_disabled_without_voice_support(qapp):

    window, _ = make_window(qapp)

    assert not window.mic.isEnabled()


def test_startup_failure_is_explained(qapp):

    def broken():
        raise RuntimeError("no api key")

    window = MainWindow(
        broken,
        settings=QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat),
        use_tray=False,
        autostart=FakeAutostart(),
    )

    assert pump(qapp, lambda: any("could not start" in t for _, t in bubbles(window)))
    assert not window.send_button.isEnabled()


def test_quit_closes_the_speaker(qapp, monkeypatch):

    speaker = FakeSpeaker()
    window, _ = make_window(qapp, speaker=speaker)

    monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: None))

    window.quit()

    assert speaker.closed


def test_autostart_menu_item_toggles_the_setting(qapp):

    autostart = FakeAutostart()

    window = MainWindow(
        lambda: FakeSophia(),
        settings=QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat),
        use_tray=False,
        autostart=autostart,
    )

    assert not window.autostart_action.isChecked()

    window.autostart_action.setChecked(True)

    assert autostart.enabled

    window.autostart_action.setChecked(False)

    assert not autostart.enabled


class StreamingSophia(FakeSophia):

    def respond(self, text, on_text=None):

        for piece in ("Sure. I can ", "do that. ", "Almost done"):
            on_text(piece)

        return {"response": "Sure. I can do that. Almost done.", "tool_used": False}


def test_the_answer_streams_into_one_bubble_and_is_spoken_by_sentence(qapp):

    speaker = FakeSpeaker()
    window, _ = make_window(qapp, StreamingSophia(), speaker=speaker)

    window.voice_toggle.setChecked(True)
    window.input.setPlainText("hello")
    window.send_from_input()

    assert pump(qapp, lambda: not window.busy)

    replies = [text for role, text in bubbles(window) if role == "bot"]

    # one bubble, holding the final text, never a duplicate
    assert replies == ["Sure. I can do that. Almost done."]

    # sentences were spoken as they completed, then the rest once
    assert speaker.said == ["Sure.", "I can do that.", "Almost done."]


def test_streamed_text_is_not_spoken_when_voice_is_off(qapp):

    speaker = FakeSpeaker()
    window, _ = make_window(qapp, StreamingSophia(), speaker=speaker)

    window.voice_toggle.setChecked(False)
    window.input.setPlainText("hello")
    window.send_from_input()

    assert pump(qapp, lambda: not window.busy)

    assert speaker.said == []


# ---------------------------------------------------------------
# Agent look: live steps, status pill, activity wording
# ---------------------------------------------------------------

def tool_event(window, phase, token, name, args=None, ok=True, seconds=0.0):

    window.tool_event.emit({
        "phase": phase, "token": token, "name": name, "args": args or {},
        "ok": ok, "message": "", "seconds": seconds,
    })


def test_tool_runs_appear_as_live_steps_and_fold_when_done(qapp):

    from app.ui.widgets import AgentSteps

    window, _ = make_window(qapp)
    window.busy = True

    tool_event(window, "start", 1, "open_application", {"name": "notepad"})
    tool_event(window, "start", 2, "get_weather", {"city": "Vizag"})
    pump(qapp, lambda: window._steps is not None)

    steps = window._steps

    assert isinstance(steps, AgentSteps)
    assert [r.label.text() for r in steps.order][0].endswith("Opening notepad")
    assert not steps.done

    tool_event(window, "end", 1, "open_application", ok=True, seconds=0.2)
    tool_event(window, "end", 2, "get_weather", ok=False, seconds=1.0)
    pump(qapp, lambda: steps.order[1].finished)

    window._on_reply({"response": "Done.", "tool_used": True})

    assert steps.done
    assert "Used 2 actions, 1 failed" in steps.title.text()

    # a failure stays visible; a clean run folds away
    assert not steps.body.isHidden()


def test_a_clean_multi_step_run_folds_to_one_line(qapp):

    window, _ = make_window(qapp)
    window.busy = True

    for i, name in enumerate(["web_search", "read_webpage"], start=1):
        tool_event(window, "start", i, name, {"query": "x", "url": "https://example.com/a"})
        tool_event(window, "end", i, name, ok=True, seconds=0.3)

    pump(qapp, lambda: window._steps is not None and window._steps.order[-1].finished)

    steps = window._steps

    window._on_reply({"response": "Here.", "tool_used": True})

    assert steps.title.text() == "Used 2 actions"
    assert steps.body.isHidden()

    steps.toggle()

    assert not steps.body.isHidden()


def test_tool_events_outside_a_request_are_ignored(qapp):

    window, _ = make_window(qapp)

    tool_event(window, "start", 1, "web_search", {"query": "x"})
    qapp.processEvents()

    assert window._steps is None


def test_steps_are_attached_to_the_real_registry(qapp):

    from app.tools.registry import Tool, ToolRegistry

    sophia = FakeSophia()
    registry = ToolRegistry()
    registry.register(Tool(name="get_current_time", description="t", handler=lambda c: "noon"))
    sophia.brain = SimpleNamespace(registry=registry, screen_policy={})

    window, _ = make_window(qapp, sophia)

    assert len(registry.observers) == 1

    window.busy = True
    registry.execute("get_current_time", {}, None)

    assert pump(qapp, lambda: window._steps is not None and window._steps.order[0].finished)


def test_status_pill_colours_follow_the_state(qapp):

    from app.ui.widgets import StatusPill

    assert StatusPill.classify("Thinking...") == "working"
    assert StatusPill.classify("Listening...") == "listening"
    assert StatusPill.classify("Listening for 'Hey Jarvis'") == "idle"
    assert StatusPill.classify("I didn't hear anything") == "problem"
    assert StatusPill.classify("Ready") == "idle"

    pill = StatusPill()
    pill.setText("Thinking...")

    assert pill.property("state") == "working"


def test_activity_wording():

    from app.ui.activity import describe_step

    assert describe_step("open_application", {"name": "Notepad"})[1] == "Opening Notepad"
    assert describe_step("get_weather", {"city": "Vizag"})[1] == "Checking the weather in Vizag"
    assert describe_step("get_weather", {})[1] == "Checking the weather"
    assert describe_step("read_webpage", {"url": "https://www.bbc.com/news/x"})[1] == "Reading www.bbc.com"
    assert describe_step("mcp_github_list_issues")[1] == "Github list issues"
    assert describe_step("some_new_tool")[1] == "Some new tool"

    long_query = "x" * 200

    assert len(describe_step("web_search", {"query": long_query})[1]) < 80
