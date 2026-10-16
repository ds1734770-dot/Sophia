import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import threading
import time

import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.widgets import Bubble
from app.voice.neural_voice import EdgeBackend
from app.voice.wakeword import COOLDOWN_SECONDS, WakeWordListener, spoken_name
from tests.test_ui import (
    FakeAutostart,
    FakeRecorder,
    FakeSophia,
    FakeSpeaker,
    FakeTranscriber,
    pump,
)


# ---------------------------------------------------------------
# Neural voice
# ---------------------------------------------------------------

class FakeOutput:

    def __init__(self):
        self.played = []
        self.stopped = 0
        self._busy_calls = 0

    def play(self, samples, rate):
        self.played.append((len(samples), rate))
        self._busy_calls = 2

    def busy(self):
        self._busy_calls -= 1
        return self._busy_calls > 0

    def stop(self):
        self.stopped += 1
        self._busy_calls = 0


class FakeSapi:

    def __init__(self):
        self.spoken = []
        self.purged = 0

    def start(self, text):
        self.spoken.append(text)

    def done(self, timeout_ms):
        return True

    def purge(self):
        self.purged += 1


def test_neural_voice_plays_synthesized_audio():

    output = FakeOutput()
    asked = []

    backend = EdgeBackend(
        voice="en-IN-NeerjaNeural",
        synthesize=lambda text, voice: asked.append((text, voice)) or b"mp3",
        decode=lambda data: (np.ones(2400, dtype="float32"), 24000),
        output=output,
    )

    backend.start("Hello")

    assert asked == [("Hello", "en-IN-NeerjaNeural")]
    assert output.played == [(2400, 24000)]
    assert backend.done(500)

    backend.purge()

    assert output.stopped == 1


def test_offline_falls_back_to_the_windows_voice():

    sapi = FakeSapi()

    def offline(text, voice):
        raise ConnectionError("no internet")

    backend = EdgeBackend(synthesize=offline, decode=lambda d: (None, 0), fallback=sapi, output=FakeOutput())

    backend.start("Hello")

    assert sapi.spoken == ["Hello"]
    assert backend.done(10)

    backend.purge()

    assert sapi.purged == 1


def test_empty_audio_also_falls_back():

    sapi = FakeSapi()

    backend = EdgeBackend(
        synthesize=lambda t, v: b"",
        decode=lambda d: (np.zeros(0, dtype="float32"), 24000),
        fallback=sapi,
        output=FakeOutput(),
    )

    backend.start("Hi")

    assert sapi.spoken == ["Hi"]


def test_without_a_fallback_the_error_is_raised():

    def offline(text, voice):
        raise ConnectionError("no internet")

    backend = EdgeBackend(synthesize=offline, output=FakeOutput())

    try:
        backend.start("x")
        raised = False

    except ConnectionError:
        raised = True

    assert raised


# ---------------------------------------------------------------
# Wake word
# ---------------------------------------------------------------

class FakeWakeModel:

    def __init__(self, scores):
        self.scores = list(scores)
        self.resets = 0

    def predict(self, chunk):
        return {"hey_jarvis": self.scores.pop(0)}

    def reset(self):
        self.resets += 1


class FakeStream:

    def __init__(self):
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        pass


def make_listener(scores, clock=None, **kwargs):

    woke = threading.Event()
    count = []

    def on_wake():
        count.append(1)
        woke.set()

    stream = FakeStream()
    model = FakeWakeModel(scores)

    listener = WakeWordListener(
        on_wake,
        model_factory=lambda name: model,
        stream_factory=lambda cb: stream,
        clock=clock or time.monotonic,
        **kwargs,
    )

    listener.start()

    return listener, woke, count, stream, model


CHUNK = np.zeros(1280, dtype="int16")


def test_wake_word_triggers_the_callback():

    listener, woke, count, stream, _ = make_listener([0.1, 0.9])

    assert stream.started and listener.running

    listener.feed(CHUNK)
    assert not woke.wait(0.1)

    listener.feed(CHUNK)
    assert woke.wait(1)
    assert len(count) == 1


def test_repeat_detections_are_debounced():

    now = [100.0]

    listener, woke, count, _, _ = make_listener([0.9, 0.9, 0.9], clock=lambda: now[0])

    listener.feed(CHUNK)
    assert woke.wait(1)

    now[0] += COOLDOWN_SECONDS / 2
    listener.feed(CHUNK)

    now[0] += COOLDOWN_SECONDS
    listener.feed(CHUNK)

    deadline = time.time() + 1

    while len(count) < 2 and time.time() < deadline:
        time.sleep(0.01)

    assert len(count) == 2


def test_paused_listener_ignores_audio_and_resume_resets_the_model():

    listener, woke, count, _, model = make_listener([0.95, 0.95])

    listener.pause()
    listener.feed(CHUNK)

    assert not woke.wait(0.1)
    assert model.scores == [0.95, 0.95]     # not even analysed

    listener.resume()

    assert model.resets == 1

    listener.feed(CHUNK)

    assert woke.wait(1)


def test_stop_closes_the_microphone():

    listener, _, _, stream, _ = make_listener([])

    listener.stop()

    assert stream.stopped and not listener.running


def test_spoken_name():

    assert spoken_name("hey_jarvis") == "Hey Jarvis"


# ---------------------------------------------------------------
# The window's hands-free flow
# ---------------------------------------------------------------

class FakeListener:

    def __init__(self, on_wake, fail=False):
        self.on_wake = on_wake
        self.word = "hey_jarvis"
        self.running = False
        self.paused = False
        self.stopped = False
        self.resumed = 0
        self.fail = fail

    def start(self):

        if self.fail:
            raise OSError("no microphone")

        self.running = True

    def stop(self):
        self.running = False
        self.stopped = True

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False
        self.resumed += 1


class TalkingSpeaker(FakeSpeaker):

    def __init__(self):
        super().__init__()
        self.speaking = threading.Event()


def make_window(qapp, sophia=None, recorder=None, listener_fail=False, speaker=None):

    holder = {}

    def wake_factory(on_wake):
        holder["listener"] = FakeListener(on_wake, fail=listener_fail)
        return holder["listener"]

    beeps = []

    window = MainWindow(
        lambda: sophia or FakeSophia(replies={"open notepad": "Opening Notepad."}),
        speaker=speaker or TalkingSpeaker(),
        recorder_factory=(lambda: recorder) if recorder else None,
        transcriber=FakeTranscriber("open notepad"),
        settings=QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat),
        use_tray=False,
        autostart=FakeAutostart(),
        wake_factory=wake_factory,
        beep=lambda: beeps.append(1),
    )

    assert pump(qapp, lambda: window.sophia is not None)

    return window, holder, beeps


def qapp():

    return QApplication.instance() or QApplication([])


def test_enabling_hands_free_starts_the_listener():

    app = qapp()

    window, holder, _ = make_window(app)

    window.hands_free_action.setChecked(True)

    assert pump(app, lambda: holder["listener"].running)
    assert pump(app, lambda: "Hey Jarvis" in window.status.text())


def test_a_failing_wake_word_is_reported_and_switched_off():

    app = qapp()

    # hands-free is on by default, so the failure happens at start-up
    window, holder, _ = make_window(app, listener_fail=True)

    assert pump(app, lambda: any("wake word" in b.text() for b in window.chat.widget().findChildren(Bubble)))
    assert not window.hands_free_action.isChecked()
    assert window.wake_listener is None


def test_wake_word_then_spoken_request_gets_a_spoken_reply():

    app = qapp()

    recorder = FakeRecorder(np.ones(16000, dtype="float32"))
    speaker = TalkingSpeaker()

    window, holder, beeps = make_window(app, recorder=recorder, speaker=speaker)

    window.hands_free_action.setChecked(True)
    assert pump(app, lambda: holder["listener"].running)

    listener = holder["listener"]

    # the wake word is heard on another thread
    threading.Thread(target=listener.on_wake).start()

    assert pump(app, lambda: recorder.started)
    assert listener.paused and beeps == [1]

    recorder.finished.set()

    assert pump(app, lambda: not window.busy and speaker.said == ["Opening Notepad."])

    # voice replies are off in the toggle, but a spoken request is answered aloud
    assert not window.voice_toggle.isChecked()

    # and Sophia listens for the wake word again
    assert pump(app, lambda: listener.resumed >= 1 and not listener.paused)


def test_listener_waits_until_sophia_has_stopped_speaking():

    app = qapp()

    speaker = TalkingSpeaker()

    window, holder, _ = make_window(app, speaker=speaker)

    window.hands_free_action.setChecked(True)
    assert pump(app, lambda: holder["listener"].running)

    listener = holder["listener"]
    listener.pause()

    speaker.speaking.set()
    window._resume_wake_when_quiet()

    pump(app, lambda: False, seconds=0.8)

    assert listener.resumed == 0

    speaker.speaking.clear()

    assert pump(app, lambda: listener.resumed == 1, seconds=3)


def test_the_wake_word_is_ignored_while_busy():

    app = qapp()

    recorder = FakeRecorder(np.ones(16000, dtype="float32"))

    window, holder, beeps = make_window(app, recorder=recorder)

    window.hands_free_action.setChecked(True)
    assert pump(app, lambda: holder["listener"].running)

    window.busy = True
    window._on_wake()

    assert beeps == [] and not recorder.started


def test_quit_stops_the_listener(monkeypatch):

    app = qapp()

    window, holder, _ = make_window(app)

    window.hands_free_action.setChecked(True)
    assert pump(app, lambda: holder["listener"].running)

    monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: None))

    window.quit()

    assert holder["listener"].stopped
