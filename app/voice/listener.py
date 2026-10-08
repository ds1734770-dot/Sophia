"""
Speech-to-text, fully local: the microphone is recorded with
sounddevice and transcribed with faster-whisper. Nothing is sent over
the network except the one-time model download, and no AI quota is used.
"""

import logging
import threading

import numpy as np

log = logging.getLogger("sophia.voice")

SAMPLE_RATE = 16000


class Recorder:
    """
    Records the microphone. Stops when stop() is called, or on its own
    after `silence_seconds` of quiet once speech was heard.
    """

    def __init__(
        self,
        silence_seconds=1.2,
        max_seconds=30,
        threshold=0.012,
        stream_factory=None,
    ):

        self.silence_seconds = silence_seconds
        self.max_seconds = max_seconds
        self.threshold = threshold

        self._stream_factory = stream_factory or self._open_stream

        self._chunks = []
        self._stream = None
        self._heard_speech = False
        self._quiet_samples = 0

        self.finished = threading.Event()

    @staticmethod
    def _open_stream(callback):

        import sounddevice as sd

        return sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=callback,
        )

    # ------------------------------------------------

    def start(self):

        self._chunks = []
        self._heard_speech = False
        self._quiet_samples = 0
        self.finished.clear()

        self._stream = self._stream_factory(self._on_audio)
        self._stream.start()

    def _on_audio(self, data, frames, time_info, status):

        chunk = np.copy(data[:, 0]) if data.ndim > 1 else np.copy(data)

        self.feed(chunk)

    def feed(self, chunk):
        """
        Take one block of audio (also the entry point for tests).
        """

        self._chunks.append(chunk)

        loud = float(np.sqrt(np.mean(chunk ** 2))) > self.threshold

        if loud:

            self._heard_speech = True
            self._quiet_samples = 0

        else:

            self._quiet_samples += len(chunk)

        total = sum(len(c) for c in self._chunks)

        if total >= self.max_seconds * SAMPLE_RATE:
            self.finished.set()

        elif (
            self._heard_speech
            and self._quiet_samples >= self.silence_seconds * SAMPLE_RATE
        ):
            self.finished.set()

    def stop(self):
        """
        Stop recording and return the audio as float32 (16 kHz mono).
        """

        if self._stream is not None:

            try:
                self._stream.stop()
                self._stream.close()

            finally:
                self._stream = None

        if not self._chunks or not self._heard_speech:
            return np.zeros(0, dtype="float32")

        return np.concatenate(self._chunks).astype("float32")


class Transcriber:
    """
    Local Whisper. The model loads the first time it is needed.
    """

    def __init__(self, model_name="base.en", model_factory=None):

        self.model_name = model_name
        self._model_factory = model_factory or self._load_model
        self._model = None

    @staticmethod
    def _load_model(name):

        from faster_whisper import WhisperModel

        return WhisperModel(name, device="cpu", compute_type="int8")

    def transcribe(self, audio):
        """
        Audio (float32, 16 kHz mono) -> text. Empty audio -> "".
        """

        if audio is None or len(audio) < SAMPLE_RATE * 0.3:
            return ""

        if self._model is None:

            log.info("Loading speech model %s", self.model_name)
            self._model = self._model_factory(self.model_name)

        segments, _ = self._model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=True,
        )

        return " ".join(s.text.strip() for s in segments).strip()
