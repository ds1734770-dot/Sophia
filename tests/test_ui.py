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

    def respond(self, text):

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

    def say(self, text):
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
    assert bubbles(window)[0][0] == "bot"
    assert "Sophia" in bubbles(window)[0][1]
    assert window.send_button.isEnabled()


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
