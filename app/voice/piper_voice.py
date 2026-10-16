"""
A natural voice that works offline: Piper (neural text-to-speech that runs
on this PC). No internet, no account, no quota, and no waiting on a
server. It speaks faster than real time on a normal laptop and starts
talking after the first sentence is ready.

The voice model (about 60 MB) is kept in Sophia's data folder and is
downloaded the first time. Loading it takes several seconds, so it is
loaded in the background when Sophia starts.
"""

import collections
import logging
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger("sophia.voice")

DEFAULT_PIPER_VOICE = "en_GB-jenny_dioco-medium"

# How long a spoken sentence may wait for the voice to load before the
# Windows voice says it instead
LOAD_WAIT_SECONDS = 1.5

# The first audio of a sentence should arrive within this time
FIRST_AUDIO_TIMEOUT = 25


# ---------------------------------------------------------------
# The voice model
# ---------------------------------------------------------------

def download_voice_files(name, folder):
    """
    Fetch the voice model into `folder` if it is not there yet.
    """

    from piper.download_voices import download_voice

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    download_voice(name, folder)


def load_piper_voice(path):

    from piper import PiperVoice

    return PiperVoice.load(path)


class PiperEngine:
    """
    The loaded voice, shared by everything that speaks. Load it with
    preload() (usually in the background); get() hands it out once ready.
    """

    def __init__(
        self,
        voice=DEFAULT_PIPER_VOICE,
        folder=None,
        loader=load_piper_voice,
        downloader=download_voice_files,
        length_scale=None,
    ):

        self.name = voice
        self.folder = Path(folder) if folder else Path("models") / "piper"
        self._loader = loader
        self._downloader = downloader
        self.length_scale = length_scale

        self._voice = None
        self.error = None

        self.ready = threading.Event()
        self._lock = threading.Lock()
        self._thread = None

    @property
    def model_path(self):

        return self.folder / f"{self.name}.onnx"

    def preload(self):
        """
        Download (first time) and load the voice. Blocks; sets `ready`
        either way (check `error`).
        """

        with self._lock:

            if self._voice is not None or self.ready.is_set():
                return

            try:

                if not self.model_path.exists() or not Path(str(self.model_path) + ".json").exists():

                    log.info("Downloading the voice '%s' (about 60 MB, once)", self.name)

                    self._downloader(self.name, self.folder)

                self._voice = self._loader(self.model_path)

                # the first sentence is slow while the engine warms up
                try:
                    for _ in self._voice.synthesize("Ready."):
                        pass

                except Exception:
                    log.debug("Voice warm-up failed", exc_info=True)

                log.info("Voice '%s' is ready", self.name)

            except Exception as e:

                self.error = e

                log.warning("The offline voice is unavailable: %s", e)

            finally:

                self.ready.set()

    def start_preload(self):

        if self._thread is None:

            self._thread = threading.Thread(
                target=self.preload, name="voice-preload", daemon=True
            )

            self._thread.start()

    def get(self, wait=0.0):
        """
        The voice, or None while it is still loading (or failed).
        """

        if not self.ready.is_set() and wait:
            self.ready.wait(wait)

        return self._voice

    def synthesis_config(self):

        if self.length_scale is None:
            return None

        from piper import SynthesisConfig

        return SynthesisConfig(length_scale=self.length_scale)


# ---------------------------------------------------------------
# Playing audio as it arrives
# ---------------------------------------------------------------

class StreamPlayer:
    """
    Plays audio chunks as they are pushed (one output stream, kept open
    between sentences so each starts without delay).
    """

    def __init__(self, stream_factory=None):

        self._stream_factory = stream_factory or self._open
        self._stream = None
        self._rate = None

        self._chunks = collections.deque()
        self._offset = 0
        self._input_done = True
        self._lock = threading.Lock()

    @staticmethod
    def _open(rate, callback):

        import sounddevice as sd

        return sd.OutputStream(
            samplerate=rate, channels=1, dtype="float32", callback=callback
        )

    def begin(self, rate):
        """
        A new sentence is coming at this sample rate.
        """

        with self._lock:

            self._chunks.clear()
            self._offset = 0
            self._input_done = False

        if self._stream is None or rate != self._rate:

            self._close_stream()

            self._stream = self._stream_factory(rate, self._callback)
            self._stream.start()

            self._rate = rate

    def push(self, samples):

        with self._lock:
            self._chunks.append(np.asarray(samples, dtype="float32"))

    def end_input(self):
        """
        No more audio is coming for this sentence.
        """

        with self._lock:
            self._input_done = True

    def finished(self):
        """
        Everything has been played.
        """

        with self._lock:
            return self._input_done and not self._chunks

    def stop(self):
        """
        Cut the sound off now.
        """

        with self._lock:

            self._chunks.clear()
            self._offset = 0
            self._input_done = True

    def _callback(self, outdata, frames, time_info, status):

        out = np.zeros(frames, dtype="float32")

        with self._lock:

            filled = 0

            while filled < frames and self._chunks:

                chunk = self._chunks[0]

                take = min(len(chunk) - self._offset, frames - filled)

                out[filled:filled + take] = chunk[self._offset:self._offset + take]

                filled += take
                self._offset += take

                if self._offset >= len(chunk):

                    self._chunks.popleft()
                    self._offset = 0

        outdata[:, 0] = out

    def _close_stream(self):

        if self._stream is not None:

            try:
                self._stream.stop()
                self._stream.close()

            except Exception:
                log.debug("Closing the voice output failed", exc_info=True)

            finally:
                self._stream = None

    def close(self):

        self.stop()
        self._close_stream()


# ---------------------------------------------------------------
# The speaker backend
# ---------------------------------------------------------------

class PiperBackend:
    """
    Speaker backend (see app.voice.speaker.Speaker): start / done / purge.
    If the offline voice is not ready, or fails, the fallback speaks.
    """

    def __init__(self, engine, fallback=None, player=None, load_wait=LOAD_WAIT_SECONDS):

        self.engine = engine
        self.fallback = fallback
        self.player = player or StreamPlayer()
        self.load_wait = load_wait

        self._using_fallback = False
        self._cancel = threading.Event()

    def _use_fallback(self, text, reason):

        if self.fallback is None:
            raise RuntimeError(reason)

        log.info("Using the Windows voice (%s)", reason)

        self._using_fallback = True

        self.fallback.start(text)

    def start(self, text):

        self._using_fallback = False
        self._cancel.clear()

        voice = self.engine.get(wait=self.load_wait)

        if voice is None:

            self._use_fallback(text, "the offline voice is still loading or unavailable")

            return

        rate = voice.config.sample_rate

        self.player.begin(rate)

        first = threading.Event()
        failure = []
        produced = []

        def produce():

            try:

                for chunk in voice.synthesize(text, self.engine.synthesis_config()):

                    if self._cancel.is_set():
                        break

                    self.player.push(chunk.audio_float_array)

                    produced.append(True)
                    first.set()

            except Exception as e:

                failure.append(e)

            finally:

                self.player.end_input()

                first.set()

        threading.Thread(target=produce, name="voice-synth", daemon=True).start()

        if not first.wait(FIRST_AUDIO_TIMEOUT) or (failure and not produced):

            self.player.stop()

            self._use_fallback(text, f"synthesis failed: {failure[0] if failure else 'timed out'}")

    def done(self, timeout_ms):

        if self._using_fallback:
            return self.fallback.done(timeout_ms)

        import time

        deadline = time.time() + timeout_ms / 1000

        while time.time() < deadline:

            if self.player.finished():
                return True

            time.sleep(0.01)

        return self.player.finished()

    def purge(self):

        self._cancel.set()

        if self._using_fallback:

            self.fallback.purge()

            return

        self.player.stop()
