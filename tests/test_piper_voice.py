import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from app.voice.piper_voice import PiperBackend, PiperEngine, StreamPlayer


# ---------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------

class FakeVoice:

    def __init__(self, chunks=3, fail_at=None, delay=0.0):

        self.config = SimpleNamespace(sample_rate=22050)
        self.chunks = chunks
        self.fail_at = fail_at
        self.delay = delay
        self.spoken = []

    def synthesize(self, text, config=None):

        self.spoken.append(text)

        for i in range(self.chunks):

            if self.fail_at == i:
                raise RuntimeError("synthesis broke")

            time.sleep(self.delay)

            yield SimpleNamespace(audio_float_array=np.full(2205, 0.1 * (i + 1), dtype="float32"))


class FakePlayer:

    def __init__(self):

        self.began = []
        self.pushed = []
        self.input_done = True
        self.stopped = 0

    def begin(self, rate):
        self.began.append(rate)
        self.input_done = False
        self.pushed = []

    def push(self, samples):
        self.pushed.append(len(samples))

    def end_input(self):
        self.input_done = True

    def finished(self):
        return self.input_done

    def stop(self):
        self.stopped += 1
        self.input_done = True


class FakeFallback:

    def __init__(self):
        self.spoken = []
        self.purged = 0

    def start(self, text):
        self.spoken.append(text)

    def done(self, timeout_ms):
        return True

    def purge(self):
        self.purged += 1


def ready_engine(voice):

    engine = PiperEngine(loader=lambda path: voice, downloader=lambda n, f: None)

    engine.preload()

    voice.spoken.clear()           # forget the engine's warm-up phrase

    return engine


# ---------------------------------------------------------------
# The engine
# ---------------------------------------------------------------

def test_the_voice_is_downloaded_once_then_loaded(tmp_path):

    downloads = []

    def downloader(name, folder):

        downloads.append(name)

        (folder / f"{name}.onnx").write_text("m")
        (folder / f"{name}.onnx.json").write_text("{}")

    engine = PiperEngine("v", tmp_path, loader=lambda path: FakeVoice(), downloader=downloader)

    engine.preload()

    assert downloads == ["v"] and engine.get() is not None and engine.error is None

    # next start-up: the files are there, nothing to download
    again = PiperEngine("v", tmp_path, loader=lambda path: FakeVoice(), downloader=downloader)

    again.preload()

    assert downloads == ["v"]


def test_a_failed_load_is_reported_not_raised(tmp_path):

    def broken(name, folder):
        raise OSError("no internet")

    engine = PiperEngine("v", tmp_path, loader=lambda p: FakeVoice(), downloader=broken)

    engine.preload()

    assert engine.ready.is_set() and engine.get() is None and "no internet" in str(engine.error)


def test_preload_in_the_background_and_waiting_for_it():

    release = threading.Event()

    def slow_loader(path):

        release.wait(2)

        return FakeVoice()

    engine = PiperEngine(loader=slow_loader, downloader=lambda n, f: None)

    engine.start_preload()

    assert engine.get() is None                       # still loading
    assert engine.get(wait=0.05) is None

    release.set()

    assert engine.get(wait=2) is not None


# ---------------------------------------------------------------
# The streaming player
# ---------------------------------------------------------------

class FakeStream:

    def __init__(self, rate, callback):

        self.rate = rate
        self.callback = callback
        self.started = False
        self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        pass

    def close(self):
        self.closed = True


def test_the_player_plays_chunks_in_order_and_then_silence():

    streams = []

    def factory(rate, callback):

        streams.append(FakeStream(rate, callback))

        return streams[-1]

    player = StreamPlayer(stream_factory=factory)

    player.begin(22050)

    player.push(np.array([0.1, 0.2, 0.3], dtype="float32"))
    player.push(np.array([0.4, 0.5], dtype="float32"))

    assert not player.finished()

    out = np.zeros((4, 1), dtype="float32")
    streams[0].callback(out, 4, None, None)

    assert list(out[:, 0]) == pytest.approx([0.1, 0.2, 0.3, 0.4])

    player.end_input()

    assert not player.finished()                      # one sample still to play

    out = np.zeros((4, 1), dtype="float32")
    streams[0].callback(out, 4, None, None)

    assert list(out[:, 0]) == pytest.approx([0.5, 0, 0, 0])
    assert player.finished()


def test_the_player_keeps_one_stream_open_between_sentences_and_can_cut_off():

    streams = []

    player = StreamPlayer(stream_factory=lambda rate, cb: streams.append(FakeStream(rate, cb)) or streams[-1])

    player.begin(22050)
    player.push(np.ones(100, dtype="float32"))
    player.end_input()

    player.begin(22050)                               # next sentence: same stream

    assert len(streams) == 1 and not player.finished()

    player.push(np.ones(100, dtype="float32"))

    player.stop()

    assert player.finished()

    out = np.ones((10, 1), dtype="float32")
    streams[0].callback(out, 10, None, None)

    assert not out.any()                              # silence after stop

    player.begin(16000)                               # a different rate needs a new stream

    assert len(streams) == 2 and streams[0].closed


# ---------------------------------------------------------------
# The backend
# ---------------------------------------------------------------

def test_speech_streams_to_the_player_chunk_by_chunk():

    voice = FakeVoice(chunks=3)
    player = FakePlayer()

    backend = PiperBackend(ready_engine(voice), fallback=FakeFallback(), player=player)

    backend.start("Hello there.")

    assert backend.done(2000)

    assert voice.spoken == ["Hello there."]
    assert player.began == [22050] and player.pushed == [2205, 2205, 2205]


def test_the_windows_voice_covers_for_a_voice_that_is_still_loading():

    engine = PiperEngine(loader=lambda p: FakeVoice(), downloader=lambda n, f: None)   # never preloaded
    fallback = FakeFallback()

    backend = PiperBackend(engine, fallback=fallback, player=FakePlayer(), load_wait=0.0)

    backend.start("Hello.")

    assert fallback.spoken == ["Hello."]
    assert backend.done(10)


def test_the_windows_voice_covers_a_broken_download():

    engine = PiperEngine(loader=lambda p: FakeVoice(), downloader=lambda n, f: (_ for _ in ()).throw(OSError("offline")))

    engine.preload()

    fallback = FakeFallback()

    PiperBackend(engine, fallback=fallback, player=FakePlayer()).start("Hi")

    assert fallback.spoken == ["Hi"]


def test_a_synthesis_error_before_any_sound_falls_back():

    player = FakePlayer()
    fallback = FakeFallback()

    backend = PiperBackend(ready_engine(FakeVoice(fail_at=0)), fallback=fallback, player=player)

    backend.start("Hi")

    assert fallback.spoken == ["Hi"] and player.stopped == 1


def test_an_error_after_some_sound_keeps_what_was_spoken():

    fallback = FakeFallback()

    backend = PiperBackend(ready_engine(FakeVoice(chunks=3, fail_at=2)), fallback=fallback, player=FakePlayer())

    backend.start("Hi")

    assert fallback.spoken == []                      # no second voice repeating the sentence


def test_purge_cuts_off_the_speech():

    voice = FakeVoice(chunks=40, delay=0.02)
    player = FakePlayer()

    backend = PiperBackend(ready_engine(voice), fallback=FakeFallback(), player=player)

    backend.start("A long sentence.")

    backend.purge()

    time.sleep(0.2)

    assert player.stopped >= 1 and len(player.pushed) < 40


def test_no_fallback_means_an_error_the_speaker_can_report():

    engine = PiperEngine(loader=lambda p: FakeVoice(), downloader=lambda n, f: None)

    with pytest.raises(RuntimeError):
        PiperBackend(engine, fallback=None, player=FakePlayer(), load_wait=0.0).start("Hi")


def test_it_works_with_the_speaker_thread():

    from app.voice.speaker import Speaker

    voice = FakeVoice(chunks=2)
    player = FakePlayer()
    engine = ready_engine(voice)

    speaker = Speaker(backend_factory=lambda: PiperBackend(engine, fallback=FakeFallback(), player=player))

    speaker.say("Hello **world**. Visit https://example.com now.")

    deadline = time.time() + 3

    while time.time() < deadline and not voice.spoken:
        time.sleep(0.01)

    speaker.close()

    # markdown and links are cleaned before the voice sees them
    assert voice.spoken == ["Hello world. Visit a link now."]
