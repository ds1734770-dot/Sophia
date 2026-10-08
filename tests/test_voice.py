import time
from types import SimpleNamespace

import numpy as np

from app.voice.listener import SAMPLE_RATE, Recorder, Transcriber
from app.voice.speaker import MAX_SPOKEN_CHARS, Speaker, speakable


# ---------------------------------------------------------------
# speakable
# ---------------------------------------------------------------

def test_markdown_is_removed():

    text = "## Plan\n\n* **Open** the [docs](https://x.com/a)\n* run `pip install`"

    assert speakable(text) == "Plan Open the docs run pip install"


def test_code_blocks_and_links_are_not_read_out():

    assert "omitted" in speakable("Try:\n```python\nprint(1)\n```\nDone")
    assert speakable("see https://example.com/very/long/path now") == "see a link now"


def test_long_text_is_cut_at_a_sentence():

    text = ("This is a sentence. " * 200).strip()

    spoken = speakable(text)

    assert len(spoken) <= MAX_SPOKEN_CHARS + 5
    assert spoken.endswith("...")
    assert "sentence. ..." in spoken


# ---------------------------------------------------------------
# Speaker
# ---------------------------------------------------------------

class FakeBackend:

    def __init__(self, hold=0.0):
        self.spoken = []
        self.purged = 0
        self.hold = hold
        self._until = 0

    def start(self, text):
        self.spoken.append(text)
        self._until = time.time() + self.hold

    def done(self, timeout_ms):
        time.sleep(min(timeout_ms / 1000, 0.01))
        return time.time() >= self._until

    def purge(self):
        self.purged += 1
        self._until = 0


def wait_for(condition, seconds=2):

    deadline = time.time() + seconds

    while time.time() < deadline:

        if condition():
            return True

        time.sleep(0.01)

    return False


def test_speaker_speaks_cleaned_text():

    backend = FakeBackend()
    speaker = Speaker(backend_factory=lambda: backend)

    speaker.say("**Hello** there")

    assert wait_for(lambda: backend.spoken == ["Hello there"])

    speaker.close()


def test_new_speech_interrupts_old_speech():

    backend = FakeBackend(hold=5)
    speaker = Speaker(backend_factory=lambda: backend)

    speaker.say("first")
    assert wait_for(lambda: backend.spoken == ["first"])

    speaker.say("second")
    assert wait_for(lambda: backend.spoken == ["first", "second"])
    assert backend.purged >= 1

    speaker.close()


def test_stop_cuts_speech_off():

    backend = FakeBackend(hold=5)
    speaker = Speaker(backend_factory=lambda: backend)

    speaker.say("a long answer")
    assert wait_for(speaker.speaking.is_set)

    speaker.stop()

    assert wait_for(lambda: not speaker.speaking.is_set())
    assert backend.purged == 1

    speaker.close()


def test_disabled_speaker_is_silent():

    backend = FakeBackend()
    speaker = Speaker(backend_factory=lambda: backend, enabled=False)

    speaker.say("hello")
    time.sleep(0.1)

    assert backend.spoken == []


def test_broken_speech_engine_disables_itself_quietly():

    def broken():
        raise OSError("no voices installed")

    speaker = Speaker(backend_factory=broken)

    speaker.say("hello")

    assert wait_for(lambda: not speaker.enabled)


# ---------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------

def block(seconds, level):

    return np.full(int(SAMPLE_RATE * seconds), level, dtype="float32")


def tone(seconds, level=0.1):
    """
    Something that is not silence once the DC offset is removed.
    """

    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE

    return (level * np.sin(2 * np.pi * 220 * t)).astype("float32")


class FakeStream:

    def __init__(self):
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        pass


def make_recorder(**kwargs):

    recorder = Recorder(stream_factory=lambda cb: FakeStream(), **kwargs)
    recorder.start()

    return recorder


def test_recorder_finishes_after_silence_following_speech():

    recorder = make_recorder(silence_seconds=1.0)

    recorder.feed(block(0.5, 0.2))
    assert not recorder.finished.is_set()

    recorder.feed(block(0.6, 0.0))
    assert not recorder.finished.is_set()

    recorder.feed(block(0.6, 0.0))
    assert recorder.finished.is_set()

    audio = recorder.stop()

    assert audio.dtype == np.float32
    assert len(audio) == int(SAMPLE_RATE * 1.7)


def test_silence_alone_never_finishes_or_returns_audio():

    recorder = make_recorder(silence_seconds=1.0)

    recorder.feed(block(3, 0.0))

    assert not recorder.finished.is_set()
    assert len(recorder.stop()) == 0


def test_recorder_has_a_time_limit():

    recorder = make_recorder(max_seconds=2)

    recorder.feed(block(2.5, 0.2))

    assert recorder.finished.is_set()


# ---------------------------------------------------------------
# Transcriber
# ---------------------------------------------------------------

class FakeModel:

    def __init__(self):
        self.calls = 0

    def transcribe(self, audio, **kwargs):
        self.calls += 1
        return [SimpleNamespace(text=" open "), SimpleNamespace(text="notepad ")], None


def test_transcriber_loads_once_and_joins_segments():

    loads = []

    def factory(name):
        loads.append(name)
        return FakeModel()

    transcriber = Transcriber("tiny.en", model_factory=factory)
    audio = tone(1)

    assert transcriber.transcribe(audio) == "open notepad"
    assert transcriber.transcribe(audio) == "open notepad"
    assert loads == ["tiny.en"]


def test_too_short_audio_is_ignored_without_loading_the_model():

    loads = []

    transcriber = Transcriber(model_factory=lambda n: loads.append(n))

    assert transcriber.transcribe(block(0.1, 0.1)) == ""
    assert transcriber.transcribe(None) == ""
    assert loads == []
