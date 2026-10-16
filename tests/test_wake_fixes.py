import logging
import threading
import time

import numpy as np
import pytest

from app.voice.wakeword import WakeWordListener, wake_decision
from tests.test_ui import FakeRecorder, FakeSophia, FakeTranscriber, make_window, pump
from tests.test_ui import qapp  # noqa: F401  (the session fixture)


# ---------------------------------------------------------------
# The rule for waking
# ---------------------------------------------------------------

def test_a_strong_score_wakes_at_once():

    assert wake_decision(0.5, 0.5, 0) == (True, 0)
    assert wake_decision(0.97, 0.5, 1) == (True, 0)


def test_a_borderline_score_needs_to_repeat():

    woke, streak = wake_decision(0.40, 0.5, 0)

    assert (woke, streak) == (False, 1)

    assert wake_decision(0.41, 0.5, streak) == (True, 2)


def test_a_single_blip_or_a_gap_does_not_wake():

    _, streak = wake_decision(0.4, 0.5, 0)

    # a low score in between resets the streak
    assert wake_decision(0.05, 0.5, streak) == (False, 0)
    assert wake_decision(0.4, 0.5, 0) == (False, 1)


def test_quiet_noise_never_wakes():

    streak = 0

    for score in (0.0, 0.1, 0.2, 0.3, 0.1, 0.0):

        woke, streak = wake_decision(score, 0.5, streak)

        assert not woke


# ---------------------------------------------------------------
# The listener uses it, and says what it hears
# ---------------------------------------------------------------

class ScriptedModel:

    def __init__(self, scores):
        self.scores = list(scores)

    def predict(self, chunk):
        return {"hey_jarvis": self.scores.pop(0) if self.scores else 0.0}

    def reset(self):
        pass


def make_listener(scores):

    heard = []
    woke = threading.Event()

    clock = {"now": 100.0}

    listener = WakeWordListener(
        on_wake=lambda: (heard.append(True), woke.set()),
        model_factory=lambda word: ScriptedModel(scores),
        stream_factory=lambda cb: None,
        clock=lambda: clock["now"],
    )

    listener._model = listener._model_factory("hey_jarvis")

    return listener, heard, woke, clock


def feed(listener, clock, count):

    for _ in range(count):

        clock["now"] += 0.08

        listener.feed(np.zeros(1280, dtype="int16"))


def test_two_borderline_blocks_in_a_row_wake_the_listener():

    listener, heard, woke, clock = make_listener([0.1, 0.38, 0.41, 0.2])

    feed(listener, clock, 4)

    assert woke.wait(1) and len(heard) == 1


def test_one_borderline_block_does_not():

    listener, heard, woke, clock = make_listener([0.1, 0.4, 0.1, 0.4, 0.1])

    feed(listener, clock, 5)

    assert not woke.wait(0.2)


def test_wakes_and_near_misses_are_written_to_the_log(caplog):

    listener, heard, woke, clock = make_listener([0.3, 0.0, 0.0, 0.9])

    with caplog.at_level(logging.INFO, logger="sophia.voice"):

        feed(listener, clock, 4)

        woke.wait(1)

    text = caplog.text

    assert "heard something (score 0.30, needs 0.50)" in text
    assert "Wake word heard (score 0.90)" in text


# ---------------------------------------------------------------
# The microphone button (it passes a "checked" flag)
# ---------------------------------------------------------------

def test_clicking_the_mic_button_starts_listening_instead_of_crashing(qapp):

    recorder = FakeRecorder(np.zeros(0, dtype="float32"))

    window, _ = make_window(
        qapp, FakeSophia(),
        recorder_factory=lambda: recorder,
        transcriber=FakeTranscriber("hello"),
    )

    window.mic.click()               # Qt calls toggle_listening(False)

    assert window.recorder is recorder and recorder.started


def test_a_bool_is_never_taken_for_audio(qapp):

    recorder = FakeRecorder(np.zeros(0, dtype="float32"))

    window, _ = make_window(
        qapp, FakeSophia(),
        recorder_factory=lambda: recorder,
        transcriber=FakeTranscriber("hello"),
    )

    window.toggle_listening(False)

    assert window.recorder is recorder


# ---------------------------------------------------------------
# A wake word that is ignored says why
# ---------------------------------------------------------------

def test_an_ignored_wake_word_is_explained_in_the_log(qapp, caplog):

    window, _ = make_window(qapp, FakeSophia())

    window.wake_listener = object()
    window.busy = True

    with caplog.at_level(logging.INFO, logger="sophia.ui"):

        window._on_wake()

    assert "Wake word ignored" in caplog.text and "busy=True" in caplog.text


# ---------------------------------------------------------------
# Start-up: the wake word does not wait for Sophia to be built
# ---------------------------------------------------------------

def test_the_wake_word_listens_before_sophia_is_ready(qapp):

    import tempfile

    from PySide6.QtCore import QSettings

    from app.ui.main_window import MainWindow
    from tests.test_ui import FakeAutostart

    started = threading.Event()
    release = threading.Event()

    class SlowStart(FakeSophia):
        pass

    def slow_factory():

        release.wait(5)

        return SlowStart()

    class Listener:

        def __init__(self, on_wake):
            self.on_wake = on_wake
            self.running = False
            self.word = "hey_jarvis"

        def start(self):
            self.running = True
            started.set()

        def stop(self):
            self.running = False

        def pause(self):
            pass

        def resume(self):
            pass

    window = MainWindow(
        slow_factory,
        settings=QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat),
        use_tray=False, autostart=FakeAutostart(),
        wake_factory=lambda on_wake: Listener(on_wake),
    )

    assert pump(qapp, lambda: started.is_set())          # listening already
    assert window.sophia is None                          # ...while she is still starting

    release.set()

    assert pump(qapp, lambda: window.sophia is not None)
    assert "Hey Jarvis" in window.status.text()           # not overwritten by "Ready"


def test_a_request_spoken_while_starting_is_answered_when_ready(qapp):

    import tempfile

    from PySide6.QtCore import QSettings

    from app.ui.main_window import MainWindow
    from tests.test_ui import FakeAutostart

    release = threading.Event()

    sophia = FakeSophia(replies={"open notepad": "Opening Notepad."})

    def slow_factory():

        release.wait(5)

        return sophia

    window = MainWindow(
        slow_factory,
        settings=QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat),
        use_tray=False, autostart=FakeAutostart(),
    )

    window.send("open notepad")

    assert sophia.received == [] and "Starting up" in window.status.text()

    release.set()

    assert pump(qapp, lambda: sophia.received == ["open notepad"])
    assert pump(qapp, lambda: not window.busy)


def test_the_speech_model_loads_once_even_when_preloaded_and_used_together():

    from app.voice.listener import Transcriber

    loads = []

    def factory(name):

        loads.append(name)
        time.sleep(0.1)

        class Model:
            def transcribe(self, audio, **kw):
                return [], None

        return Model()

    transcriber = Transcriber(model_factory=factory)

    warm = threading.Thread(target=transcriber.preload)
    warm.start()

    transcriber.transcribe(np.sin(np.linspace(0, 400, 16000)).astype("float32") * 0.3)

    warm.join()

    assert loads == ["base.en"]
