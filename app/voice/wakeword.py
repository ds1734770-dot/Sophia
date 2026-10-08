"""
Hands-free activation: listens to the microphone for a wake word
("Hey Jarvis") with a small local model (openwakeword), and calls
on_wake() when it hears it. Audio never leaves the computer.

Built to keep running for as long as Sophia does:

- the audio callback only queues audio; a worker thread runs the model, so
  a slow or failing prediction can never stop the microphone
- a watchdog reopens the microphone if audio stops arriving (device
  unplugged, sleep and wake, another program grabbing it)
- the last few seconds of audio are kept, so a request spoken right after
  the wake word is not lost, and the room's noise level is tracked
"""

import collections
import logging
import queue
import threading
import time

import numpy as np

log = logging.getLogger("sophia.voice")

SAMPLE_RATE = 16000
BLOCK = 1280          # 80 ms, what openwakeword expects
THRESHOLD = 0.5
COOLDOWN_SECONDS = 3.0

# no audio for this long means the microphone stream has died
STALL_SECONDS = 4.0
RESTART_BACKOFF = (1.0, 3.0, 8.0, 20.0)

RING_SECONDS = 4.0
NOISE_WINDOW_BLOCKS = 150        # about 12 seconds

DEFAULT_WAKE_WORD = "hey_jarvis"


def spoken_name(model):

    return model.replace("_", " ").title()


def load_wake_model(name):
    """
    The openwakeword model, downloading its small file on first use.
    """

    import glob
    import os

    from openwakeword.model import Model
    from openwakeword.utils import download_models

    from app.settings.paths import DATA_DIR

    # Kept in Sophia's data folder: the install folder may be read-only
    folder = DATA_DIR / "models"

    folder.mkdir(parents=True, exist_ok=True)

    found = glob.glob(str(folder / f"{name}*.onnx"))

    if not found:

        download_models(model_names=[name], target_directory=str(folder))

        found = glob.glob(str(folder / f"{name}*.onnx"))

    return Model(
        wakeword_models=[found[0]],
        inference_framework="onnx",
        melspec_model_path=os.path.join(folder, "melspectrogram.onnx"),
        embedding_model_path=os.path.join(folder, "embedding_model.onnx"),
    )


def open_input_stream(callback):

    import sounddevice as sd

    return sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=BLOCK,
        callback=callback,
    )


class WakeWordListener:

    def __init__(
        self,
        on_wake,
        word=DEFAULT_WAKE_WORD,
        threshold=THRESHOLD,
        model_factory=load_wake_model,
        stream_factory=open_input_stream,
        clock=time.monotonic,
    ):

        self.on_wake = on_wake
        self.word = word
        self.threshold = threshold

        self._model_factory = model_factory
        self._stream_factory = stream_factory
        self._clock = clock

        self._model = None
        self._stream = None
        self._paused = False
        self._last_wake = -COOLDOWN_SECONDS
        self.last_wake_time = None

        self._queue = queue.Queue(maxsize=400)
        self._ring = collections.deque()
        self._levels = collections.deque(maxlen=NOISE_WINDOW_BLOCKS)
        self._ring_lock = threading.Lock()

        self._thread = None
        self._last_audio = clock()
        self._restarts = 0
        self._next_restart = 0.0
        self._errors_logged = 0

        self.running = False

    # ------------------------------------------------
    # Start and stop
    # ------------------------------------------------

    def start(self):
        """
        Load the model and open the microphone. May raise (no
        microphone, no network for the first download).
        """

        if self.running:
            return

        self._model = self._model_factory(self.word)

        self._open_stream()

        self.running = True

        self._thread = threading.Thread(
            target=self._run, name="wake-word", daemon=True
        )

        self._thread.start()

        log.info("Listening for the wake word '%s'", self.word)

    def _open_stream(self):

        self._stream = self._stream_factory(self._on_audio)
        self._stream.start()

        self._last_audio = self._clock()

    def _close_stream(self):

        if self._stream is not None:

            try:
                self._stream.stop()
                self._stream.close()

            except Exception:
                log.debug("Closing the microphone stream failed", exc_info=True)

            finally:
                self._stream = None

    def stop(self):

        self.running = False

        self._close_stream()

        if self._thread is not None:

            self._thread.join(timeout=2)
            self._thread = None

    def pause(self):
        """
        Ignore audio (while Sophia is talking or recording).
        """

        self._paused = True

    def resume(self):

        if self._model is not None:

            try:
                self._model.reset()

            except Exception:
                log.debug("Resetting the wake model failed", exc_info=True)

        # forget anything queued while paused
        try:

            while True:
                self._queue.get_nowait()

        except queue.Empty:
            pass

        self._paused = False

    # ------------------------------------------------
    # Audio in
    # ------------------------------------------------

    def _on_audio(self, data, frames, time_info, status):
        """
        The audio thread: copy the block and hand it over. Nothing here
        may be slow or raise.
        """

        chunk = np.copy(data[:, 0]) if data.ndim > 1 else np.copy(data)

        self._last_audio = self._clock()

        try:
            self._queue.put_nowait((self._last_audio, chunk))

        except queue.Full:

            # the worker is behind: drop the oldest block
            try:
                self._queue.get_nowait()
                self._queue.put_nowait((self._last_audio, chunk))

            except (queue.Empty, queue.Full):
                pass

    def _run(self):

        while self.running:

            try:
                stamp, chunk = self._queue.get(timeout=0.5)

            except queue.Empty:

                self._watchdog()

                continue

            try:
                self._process(stamp, chunk)

            except Exception:

                # one bad block must never end listening
                if self._errors_logged < 5:

                    self._errors_logged += 1
                    log.exception("Wake word processing failed")

    def _process(self, stamp, chunk):

        if self._paused:
            return

        samples = chunk.astype("float32")

        if chunk.dtype == np.int16:
            samples = samples / 32768.0

        with self._ring_lock:

            self._ring.append((stamp, samples))

            horizon = stamp - RING_SECONDS

            while self._ring and self._ring[0][0] < horizon:
                self._ring.popleft()

            self._levels.append(float(np.sqrt(np.mean(samples ** 2))))

        self.feed(chunk, stamp)

    # ------------------------------------------------
    # Watchdog
    # ------------------------------------------------

    def _watchdog(self):
        """
        Reopen the microphone if no audio has arrived for a while.
        """

        if not self.running:
            return

        now = self._clock()

        stalled = now - self._last_audio > STALL_SECONDS

        active = getattr(self._stream, "active", True)

        if not stalled and active:

            self._restarts = 0

            return

        if now < self._next_restart:
            return

        delay = RESTART_BACKOFF[min(self._restarts, len(RESTART_BACKOFF) - 1)]

        self._restarts += 1
        self._next_restart = now + delay

        log.warning("Microphone stalled; reopening it (attempt %d)", self._restarts)

        self._close_stream()

        try:
            self._open_stream()

        except Exception as e:

            log.warning("Could not reopen the microphone: %s", e)

    # ------------------------------------------------
    # What was heard
    # ------------------------------------------------

    def audio_since(self, moment):
        """
        The audio captured from `moment` (a clock reading) until now, as
        float32 in [-1, 1].
        """

        with self._ring_lock:
            chunks = [c for t, c in self._ring if t >= moment]

        if not chunks:
            return np.zeros(0, dtype="float32")

        return np.concatenate(chunks)

    @property
    def noise_floor(self):
        """
        The room's background level (0 to 1), from the quietest part of
        the last few seconds.
        """

        with self._ring_lock:
            levels = list(self._levels)

        if len(levels) < 20:
            return 0.004

        return float(np.percentile(levels, 20))

    def feed(self, chunk, stamp=None):
        """
        One block of int16 audio: run the wake word model on it (also
        the entry point for tests).
        """

        if self._paused or self._model is None:
            return

        scores = self._model.predict(chunk)

        score = max(scores.values()) if scores else 0.0

        now = self._clock() if stamp is None else stamp

        if score >= self.threshold and now - self._last_wake >= COOLDOWN_SECONDS:

            self._last_wake = now
            self.last_wake_time = now

            # the callback may be slow (it opens the recorder): do not
            # block the audio worker
            threading.Thread(target=self.on_wake, daemon=True).start()
