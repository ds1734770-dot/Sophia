"""
Hands-free activation: listens to the microphone for a wake word
("Hey Jarvis") with a small local model (openwakeword), and calls
on_wake() when it hears it. Audio never leaves the computer.
"""

import logging
import threading
import time

import numpy as np

log = logging.getLogger("sophia.voice")

SAMPLE_RATE = 16000
BLOCK = 1280          # 80 ms, what openwakeword expects
THRESHOLD = 0.5
COOLDOWN_SECONDS = 3.0

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

        self.running = False

    # ------------------------------------------------

    def start(self):
        """
        Load the model and open the microphone. May raise (no
        microphone, no network for the first download).
        """

        if self.running:
            return

        self._model = self._model_factory(self.word)

        self._stream = self._stream_factory(self._on_audio)
        self._stream.start()

        self.running = True

        log.info("Listening for the wake word '%s'", self.word)

    def stop(self):

        self.running = False

        if self._stream is not None:

            try:
                self._stream.stop()
                self._stream.close()

            finally:
                self._stream = None

    def pause(self):
        """
        Ignore audio (while Sophia is talking or recording).
        """

        self._paused = True

    def resume(self):

        if self._model is not None:
            self._model.reset()

        self._paused = False

    # ------------------------------------------------

    def _on_audio(self, data, frames, time_info, status):

        chunk = np.copy(data[:, 0]) if data.ndim > 1 else np.copy(data)

        self.feed(chunk)

    def feed(self, chunk):
        """
        One block of int16 audio (also the entry point for tests).
        """

        if self._paused or self._model is None:
            return

        scores = self._model.predict(chunk)

        score = max(scores.values()) if scores else 0.0

        now = self._clock()

        if score >= self.threshold and now - self._last_wake >= COOLDOWN_SECONDS:

            self._last_wake = now

            # the callback may be slow (it opens the recorder): do not
            # block the audio thread
            threading.Thread(target=self.on_wake, daemon=True).start()
