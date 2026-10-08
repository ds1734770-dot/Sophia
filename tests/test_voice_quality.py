import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QSettings
from PySide6.QtWidgets import QApplication

from app.ui.floating_car import CarController, FloatingCar
from app.ui.main_window import MainWindow
from app.voice.listener import (
    SAMPLE_RATE,
    Recorder,
    Transcriber,
    clean_text,
    prepare_audio,
)
from app.voice.wakeword import STALL_SECONDS, WakeWordListener
from tests.test_ui import FakeAutostart, FakeSophia, FakeSpeaker, FakeTranscriber, pump


def block(seconds, level):

    return np.full(int(SAMPLE_RATE * seconds), level, dtype="float32")


def tone(seconds, level=0.1):

    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE

    return (level * np.sin(2 * np.pi * 220 * t)).astype("float32")


class FakeStream:

    def __init__(self):
        self.started = self.stopped = False
        self.active = True

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        pass


# ---------------------------------------------------------------
# Levelling the audio
# ---------------------------------------------------------------

def test_quiet_speech_is_boosted_for_whisper():

    quiet = tone(1, 0.05) + 0.3          # quiet, with a DC offset

    leveled = prepare_audio(quiet)

    assert abs(float(np.mean(leveled))) < 0.01
    assert 0.85 < float(np.max(np.abs(leveled))) <= 0.9001


def test_boost_is_limited_and_silence_is_rejected():

    assert prepare_audio(block(1, 0.0)) is None
    assert prepare_audio(block(1, 0.2)) is None          # constant: nothing but DC

    faint = tone(1, 0.005)

    assert float(np.max(np.abs(prepare_audio(faint)))) <= 0.005 * 25 + 0.01


# ---------------------------------------------------------------
# Cleaning the transcript
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "heard, expected",
    [
        ("Hey Jarvis, open notepad", "open notepad"),
        ("hey jarvis open notepad", "open notepad"),
        ("Jarvis. What's the weather", "What's the weather"),
        ("ask Sofia to open chrome", "ask Sophia to open chrome"),
        ("Sophie, remind me at six", "remind me at six"),
        ("  open YouTube  ", "open YouTube"),
        ("you", ""),
        ("Thank you.", ""),
        ("Thanks for watching!", ""),
        ("", ""),
        ("Hey Jarvis", ""),
    ],
)
def test_clean_text(heard, expected):

    assert clean_text(heard) == expected


class Segment:

    def __init__(self, text, no_speech=0.0, logprob=-0.2):
        self.text = text
        self.no_speech_prob = no_speech
        self.avg_logprob = logprob


class RecordingModel:

    def __init__(self, segments):
        self.segments = segments
        self.kwargs = None
        self.audio = None

    def transcribe(self, audio, **kwargs):
        self.audio, self.kwargs = audio, kwargs
        return self.segments, None


def test_whisper_gets_levelled_audio_a_wide_search_and_the_vocabulary_hint():

    model = RecordingModel([Segment("open notepad")])

    transcriber = Transcriber(model_factory=lambda name: model)

    assert transcriber.transcribe(tone(1, 0.05)) == "open notepad"

    assert model.kwargs["beam_size"] == 5
    assert model.kwargs["language"] == "en"
    assert model.kwargs["condition_on_previous_text"] is False
    assert "YouTube" in model.kwargs["initial_prompt"]
    assert float(np.max(np.abs(model.audio))) > 0.8


def test_segments_that_are_probably_noise_are_dropped():

    model = RecordingModel([
        Segment("open notepad"),
        Segment("thanks for watching", no_speech=0.9, logprob=-1.5),
    ])

    assert Transcriber(model_factory=lambda n: model).transcribe(tone(1)) == "open notepad"


def test_silence_never_reaches_the_model():

    loads = []

    transcriber = Transcriber(model_factory=lambda n: loads.append(n))

    assert transcriber.transcribe(block(1, 0.0)) == ""
    assert loads == []


def test_a_transcript_that_is_only_a_false_phrase_is_empty():

    model = RecordingModel([Segment("Thank you.")])

    assert Transcriber(model_factory=lambda n: model).transcribe(tone(1)) == ""


# ---------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------

def make_recorder(**kwargs):

    recorder = Recorder(stream_factory=lambda cb: FakeStream(), **kwargs)
    recorder.start()

    return recorder


def test_the_start_up_chime_is_not_recorded():

    recorder = make_recorder(skip_seconds=0.35)

    recorder.feed(block(0.2, 0.3))           # chime (dropped)
    recorder.feed(block(0.2, 0.3))           # still chime / partly dropped

    assert not recorder.heard_speech or recorder._skipped >= 0.35 * SAMPLE_RATE

    recorder.feed(block(0.3, 0.2))           # now the user

    assert recorder.heard_speech


def test_a_chime_alone_does_not_count_as_speech():

    recorder = make_recorder(skip_seconds=0.4)

    recorder.feed(block(0.2, 0.5))
    recorder.feed(block(0.2, 0.5))

    recorder.feed(block(2.0, 0.0))

    assert not recorder.finished.is_set()
    assert len(recorder.stop()) == 0


def test_a_click_is_too_short_to_be_speech():

    recorder = make_recorder(min_speech_seconds=0.25)

    recorder.feed(block(0.05, 0.5))
    recorder.feed(block(3.0, 0.0))

    assert not recorder.finished.is_set()
    assert len(recorder.stop()) == 0


def test_preroll_is_kept_at_the_start():

    recorder = Recorder(stream_factory=lambda cb: FakeStream())

    recorder.start(preroll=np.full(1600, 0.5, dtype="float32"))

    recorder.feed(block(0.5, 0.2))
    recorder.feed(block(1.3, 0.0))

    audio = recorder.stop()

    assert len(audio) == 1600 + int(0.5 * SAMPLE_RATE) + int(1.3 * SAMPLE_RATE)
    assert audio[0] == pytest.approx(0.5)


def test_the_threshold_rises_above_a_noisy_room():

    quiet_room = make_recorder(noise_floor=0.002)
    noisy_room = make_recorder(noise_floor=0.01)

    assert quiet_room.effective_threshold() == pytest.approx(0.006)
    assert noisy_room.effective_threshold() == pytest.approx(0.03)

    # hiss at 0.015 is speech in a quiet room, but only noise here
    noisy_room.feed(block(1.0, 0.015))

    assert not noisy_room.heard_speech


def test_the_room_noise_is_measured_when_it_is_not_known():

    recorder = make_recorder()

    for _ in range(12):
        recorder.feed(block(0.08, 0.01))          # steady hiss

    assert recorder.effective_threshold() == pytest.approx(0.03, abs=0.002)

    recorder.feed(block(0.5, 0.2))

    assert recorder.heard_speech


def test_a_pause_in_a_sentence_does_not_end_the_recording():

    recorder = make_recorder(silence_seconds=1.1)

    recorder.feed(block(0.6, 0.2))
    recorder.feed(block(0.8, 0.0))           # a pause to think
    recorder.feed(block(0.6, 0.2))

    assert not recorder.finished.is_set()

    recorder.feed(block(1.2, 0.0))

    assert recorder.finished.is_set()


# ---------------------------------------------------------------
# Wake word that keeps running
# ---------------------------------------------------------------

CHUNK = np.zeros(1280, dtype="int16")


class FakeModel:

    def __init__(self, scores=None, fail_on=()):
        self.scores = list(scores or [])
        self.fail_on = set(fail_on)
        self.calls = 0
        self.resets = 0

    def predict(self, chunk):

        self.calls += 1

        if self.calls in self.fail_on:
            raise RuntimeError("model hiccup")

        return {"hey_jarvis": self.scores.pop(0) if self.scores else 0.0}

    def reset(self):
        self.resets += 1


def make_listener(model=None, streams=None, clock=time.monotonic, on_wake=None):

    streams = streams if streams is not None else []

    def factory(callback):

        stream = FakeStream()
        stream.callback = callback
        streams.append(stream)

        return stream

    listener = WakeWordListener(
        on_wake or (lambda: None),
        model_factory=lambda name: model or FakeModel(),
        stream_factory=factory,
        clock=clock,
    )

    return listener, streams


def push(listener, count=1, value=0):

    for _ in range(count):

        data = np.full((1280, 1), value, dtype="int16")

        listener._on_audio(data, 1280, None, None)


def wait_for(condition, seconds=3):

    deadline = time.time() + seconds

    while time.time() < deadline:

        if condition():
            return True

        time.sleep(0.01)

    return False


def test_the_audio_callback_only_queues_so_the_model_runs_off_the_audio_thread():

    model = FakeModel()

    listener, _ = make_listener(model)

    listener.start()

    main_thread = threading.get_ident()
    seen = []

    original = model.predict

    def spy(chunk):
        seen.append(threading.get_ident())
        return original(chunk)

    model.predict = spy

    push(listener, 3)

    assert wait_for(lambda: len(seen) == 3)
    assert main_thread not in seen

    listener.stop()


def test_a_failing_prediction_does_not_stop_listening():

    model = FakeModel(fail_on={1, 2}, scores=[0, 0, 0, 0.95])

    woke = threading.Event()

    listener, _ = make_listener(model, on_wake=woke.set)
    listener.start()

    push(listener, 8)

    assert woke.wait(3)

    listener.stop()


def test_the_wake_word_works_again_and_again_over_a_long_session():

    now = [1000.0]

    count = []

    model = FakeModel(scores=[0.9, 0, 0, 0.9, 0, 0, 0.9])

    listener, _ = make_listener(model, clock=lambda: now[0], on_wake=lambda: count.append(1))
    listener.start()

    for _ in range(7):

        push(listener)
        now[0] += 5            # well past the cooldown

        time.sleep(0.05)

    assert wait_for(lambda: len(count) == 3)

    listener.stop()


def test_a_stalled_microphone_is_reopened():

    now = [0.0]

    listener, streams = make_listener(clock=lambda: now[0])
    listener.start()

    assert len(streams) == 1

    # no audio for longer than the stall limit
    now[0] += STALL_SECONDS + 1

    assert wait_for(lambda: len(streams) >= 2)
    assert streams[0].stopped and streams[1].started

    listener.stop()


def test_a_dead_stream_is_reopened_even_if_audio_seems_recent():

    listener, streams = make_listener()
    listener.start()

    streams[0].active = False

    assert wait_for(lambda: len(streams) >= 2, seconds=4)

    listener.stop()


def test_failing_to_reopen_the_microphone_does_not_crash_the_watchdog():

    now = [0.0]

    streams = []
    attempts = []

    def factory(callback):

        attempts.append(1)

        if len(attempts) > 1:
            raise OSError("device busy")

        stream = FakeStream()
        streams.append(stream)

        return stream

    listener = WakeWordListener(
        lambda: None, model_factory=lambda n: FakeModel(), stream_factory=factory, clock=lambda: now[0]
    )

    listener.start()

    now[0] += STALL_SECONDS + 1

    assert wait_for(lambda: len(attempts) >= 2)
    assert listener.running and listener._thread.is_alive()

    listener.stop()


def test_audio_since_returns_what_was_said_after_the_wake_word():

    now = [100.0]

    listener, _ = make_listener(clock=lambda: now[0])
    listener.start()

    for value in (1000, 2000, 3000, 4000):

        push(listener, value=value)
        now[0] += 0.08

        time.sleep(0.03)

    assert wait_for(lambda: len(listener.audio_since(0)) == 4 * 1280)

    recent = listener.audio_since(100.0 + 0.08 * 2 - 0.001)

    assert len(recent) == 2 * 1280
    assert recent[0] == pytest.approx(3000 / 32768)

    listener.stop()


def test_old_audio_is_dropped_from_the_buffer():

    now = [0.0]

    listener, _ = make_listener(clock=lambda: now[0])
    listener.start()

    push(listener)
    time.sleep(0.05)

    now[0] += 10

    push(listener)

    assert wait_for(lambda: len(listener.audio_since(0)) == 1280)

    listener.stop()


def test_the_noise_floor_follows_the_quiet_parts_of_the_room():

    listener, _ = make_listener()
    listener.start()

    assert listener.noise_floor == 0.004          # not enough audio yet

    push(listener, 30, value=300)                  # steady background

    assert wait_for(lambda: len(listener._levels) >= 30)

    assert listener.noise_floor == pytest.approx(300 / 32768, rel=0.05)

    listener.stop()


def test_resume_clears_audio_that_arrived_while_paused():

    model = FakeModel()

    listener, _ = make_listener(model)
    listener.start()

    listener.pause()
    push(listener, 5)

    listener.resume()

    time.sleep(0.2)

    assert model.calls == 0 and model.resets == 1

    listener.stop()


# ---------------------------------------------------------------
# The wake word with the car and the chat window
# ---------------------------------------------------------------

def qapp():

    return QApplication.instance() or QApplication([])


def fresh_settings():

    return QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat)


class FakeListener:

    def __init__(self, on_wake):
        self.on_wake = on_wake
        self.word = "hey_jarvis"
        self.running = False
        self.paused = False
        self.last_wake_time = 50.0
        self.noise_floor = 0.01
        self.asked_since = []

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def audio_since(self, moment):

        self.asked_since.append(moment)

        return np.full(1600, 0.3, dtype="float32")


class CapturingRecorder:

    def __init__(self):
        self.finished = threading.Event()
        self.started = False
        self.started_with = None
        self.skip_seconds = 0.0
        self.noise_floor = None
        self.level = 0.0

    def start(self, preroll=None):
        self.started = True
        self.started_with = preroll

    def stop(self):
        return np.ones(16000, dtype="float32")


class MouseAway:

    def __call__(self):
        return QPoint(-9000, -9000)


def make_setup(app, recorder, speaker=None):

    holder = {}

    def wake_factory(on_wake):

        holder["listener"] = FakeListener(on_wake)

        return holder["listener"]

    window = MainWindow(
        lambda: FakeSophia(replies={"open notepad": "Opening Notepad."}),
        speaker=speaker or FakeSpeaker(),
        recorder_factory=lambda: recorder,
        transcriber=FakeTranscriber("open notepad"),
        settings=fresh_settings(),
        use_tray=False,
        autostart=FakeAutostart(),
        wake_factory=wake_factory,
    )

    assert pump(app, lambda: window.sophia is not None)

    car = FloatingCar(settings=fresh_settings(), cursor=MouseAway())
    CarController(window, car)

    car.show()

    return window, car, holder


def test_hands_free_is_on_by_default_without_touching_the_menu():

    app = qapp()

    window, car, holder = make_setup(app, CapturingRecorder())

    assert pump(app, lambda: "listener" in holder and holder["listener"].running)
    assert window.hands_free_action.isChecked()


def test_hands_free_stays_off_if_the_user_turned_it_off():

    app = qapp()

    settings = fresh_settings()
    settings.setValue("hands_free", False)

    holder = {}

    window = MainWindow(
        lambda: FakeSophia(),
        recorder_factory=lambda: CapturingRecorder(),
        transcriber=FakeTranscriber("x"),
        settings=settings,
        use_tray=False,
        autostart=FakeAutostart(),
        wake_factory=lambda cb: holder.setdefault("l", FakeListener(cb)),
    )

    assert pump(app, lambda: window.sophia is not None)

    pump(app, lambda: False, seconds=0.2)

    assert "l" not in holder and not window.hands_free_action.isChecked()


def test_the_wake_word_keeps_the_start_of_the_request():

    app = qapp()

    recorder = CapturingRecorder()

    window, car, holder = make_setup(app, recorder)

    assert pump(app, lambda: holder["listener"].running)

    threading.Thread(target=holder["listener"].on_wake).start()

    assert pump(app, lambda: recorder.started)

    assert holder["listener"].asked_since == [pytest.approx(49.9)]
    assert len(recorder.started_with) == 1600

    # tuned to the room, and the chime is not skipped away from real speech
    assert recorder.noise_floor == 0.01
    assert recorder.skip_seconds == 0.0


def test_the_wake_word_brings_a_hidden_car_out_and_starts_listening():

    app = qapp()

    recorder = CapturingRecorder()
    sounds = SimpleNamespace(played=[], play=lambda n: sounds.played.append(n), set_enabled=lambda on: None)

    window, car, holder = make_setup(app, recorder)

    car.sounds = sounds

    car.hide_away()

    assert pump(app, lambda: not car.isVisible(), seconds=4)

    sounds.played.clear()          # the drive-away sound is not what we are testing

    threading.Thread(target=holder["listener"].on_wake).start()

    # it starts listening straight away, while the car drives in
    assert pump(app, lambda: recorder.started)
    assert pump(app, lambda: car.isVisible() and car.model.state == "listening")

    assert pump(app, lambda: not car.driving, seconds=4)

    # driving in and listening make no engine, honk or chime sound
    assert sounds.played == []


def test_a_visible_car_just_listens_without_a_chime():

    app = qapp()

    recorder = CapturingRecorder()
    sounds = SimpleNamespace(played=[], play=lambda n: sounds.played.append(n), set_enabled=lambda on: None)

    window, car, holder = make_setup(app, recorder)

    car.sounds = sounds

    threading.Thread(target=holder["listener"].on_wake).start()

    assert pump(app, lambda: car.model.state == "listening")

    assert "listen" not in sounds.played


def test_the_button_path_still_chimes_and_skips_the_chime_in_the_recording():

    app = qapp()

    recorder = CapturingRecorder()
    sounds = SimpleNamespace(played=[], play=lambda n: sounds.played.append(n), set_enabled=lambda on: None)

    window, car, holder = make_setup(app, recorder)

    car.sounds = sounds

    window.start_voice_turn()

    assert pump(app, lambda: car.model.state == "listening")

    assert "listen" in sounds.played
    assert recorder.skip_seconds == 0.35
    assert not recorder.started or recorder.started_with is None


def test_a_wake_while_busy_is_ignored():

    app = qapp()

    recorder = CapturingRecorder()

    window, car, holder = make_setup(app, recorder)

    window.busy = True

    holder["listener"].on_wake()

    pump(app, lambda: False, seconds=0.2)

    assert not recorder.started
