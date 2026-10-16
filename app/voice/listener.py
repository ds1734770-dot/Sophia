"""
Speech-to-text, fully local: the microphone is recorded with
sounddevice and transcribed with faster-whisper. Nothing is sent over
the network except the one-time model download, and no AI quota is used.

What makes it accurate on a quiet laptop microphone:

- the audio is levelled (DC removed, quiet speech boosted) before Whisper
- the speech/silence threshold adapts to the room's background noise
- the start of a request after the wake word is not lost (pre-roll)
- Whisper gets a wider search and a vocabulary hint of Sophia's commands
- silence and noise that Whisper "hears" as phrases are discarded
"""

import logging
import os
import re
import threading

import numpy as np

log = logging.getLogger("sophia.voice")

SAMPLE_RATE = 16000

# Whisper tends to invent these when it is given noise or silence
HALLUCINATIONS = {
    "you", "thank you", "thanks", "thanks for watching", "thank you for watching",
    "bye", "bye bye", "okay", "so", "the", "uh", "um", "hmm",
}

# A hint about what people say to Sophia: it biases recognition toward
# these words and names.
VOCABULARY_HINT = (
    "Voice commands for Sophia, a computer assistant: open Chrome, YouTube, "
    "WhatsApp, Notepad, Visual Studio Code, Spotify, search the web, remind me, "
    "set a timer, weather, volume, screenshot, downloads, resume, to-do list, "
    "close, minimize, find a file, summarize."
)

NAME_FIXES = [
    (re.compile(r"\b(sofia|sophie|sofie|sofya|sophea|sophya)\b", re.IGNORECASE), "Sophia"),
    (re.compile(r"\bjarvis\b", re.IGNORECASE), "Jarvis"),
]

# "Hey Jarvis, open notepad" -> "open notepad"
WAKE_PREFIX = re.compile(r"^\s*(?:hey|hi|okay|ok)?[ ,]*(?:jarvis|sophia)\b[ ,.:!?-]*", re.IGNORECASE)


# ---------------------------------------------------------------
# Recording
# ---------------------------------------------------------------

class Recorder:
    """
    Records the microphone. Stops when stop() is called, or on its own
    after `silence_seconds` of quiet once speech was heard.

    threshold is the quietest level counted as speech; when the room's
    noise level is known (noise_floor) or measured at the start, the
    threshold rises above it so background noise does not keep the
    recording open (or end it too early).
    """

    def __init__(
        self,
        silence_seconds=1.1,
        max_seconds=30,
        threshold=0.002,
        stream_factory=None,
        noise_floor=None,
        skip_seconds=0.0,
        min_speech_seconds=0.25,
    ):

        self.silence_seconds = silence_seconds
        self.max_seconds = max_seconds
        self.threshold = threshold
        self.noise_floor = noise_floor
        self.skip_seconds = skip_seconds
        self.min_speech_seconds = min_speech_seconds

        self._stream_factory = stream_factory or self._open_stream

        self._chunks = []
        self._stream = None
        self._loud_samples = 0
        self._quiet_samples = 0
        self._skipped = 0
        self._calibration = []
        self.level = 0.0

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

    def start(self, preroll=None):
        """
        Start recording. `preroll` is audio captured just before now
        (for example the moment after the wake word) that is kept at
        the start of the recording.
        """

        self._chunks = []
        self._loud_samples = 0
        self._quiet_samples = 0
        self._skipped = 0
        self._calibration = []
        self.finished.clear()

        if preroll is not None and len(preroll):
            self._chunks.append(np.asarray(preroll, dtype="float32"))

        self._stream = self._stream_factory(self._on_audio)
        self._stream.start()

    def _on_audio(self, data, frames, time_info, status):

        chunk = np.copy(data[:, 0]) if data.ndim > 1 else np.copy(data)

        self.feed(chunk)

    @property
    def heard_speech(self):

        return self._loud_samples >= self.min_speech_seconds * SAMPLE_RATE

    def effective_threshold(self):
        """
        The level that counts as speech right now.
        """

        floor = self.noise_floor

        if floor is None and self._calibration:
            floor = float(np.percentile(self._calibration, 25))

        if floor is None:
            return self.threshold

        return max(self.threshold, min(0.05, floor * 3.0))

    def feed(self, chunk):
        """
        Take one block of audio (also the entry point for tests).
        """

        # the first moments can hold the start-up chime: ignore them
        if self._skipped < self.skip_seconds * SAMPLE_RATE:

            self._skipped += len(chunk)

            return

        self._chunks.append(chunk)

        rms = float(np.sqrt(np.mean(chunk ** 2)))

        # loudness for the on-screen car (0 to 1)
        self.level = min(1.0, rms * 12)

        # measure the room's noise during the first moments
        if self.noise_floor is None and len(self._calibration) < 12:
            self._calibration.append(rms)

        if rms > self.effective_threshold():

            self._loud_samples += len(chunk)
            self._quiet_samples = 0

        else:

            self._quiet_samples += len(chunk)

        total = sum(len(c) for c in self._chunks)

        if total >= self.max_seconds * SAMPLE_RATE:
            self.finished.set()

        elif (
            self.heard_speech
            and self._quiet_samples >= self.silence_seconds * SAMPLE_RATE
        ):
            self.finished.set()

    def stop(self):
        """
        Stop recording and return the audio as float32 (16 kHz mono),
        or an empty array if nobody spoke.
        """

        if self._stream is not None:

            try:
                self._stream.stop()
                self._stream.close()

            finally:
                self._stream = None

        if not self._chunks or not self.heard_speech:
            return np.zeros(0, dtype="float32")

        return np.concatenate(self._chunks).astype("float32")


# ---------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------

def prepare_audio(audio):
    """
    Level the audio for Whisper: remove DC offset and boost quiet
    speech (never more than 25x). Returns None if it is just silence.
    """

    audio = np.asarray(audio, dtype="float32")

    audio = audio - float(np.mean(audio))

    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0

    if peak < 0.004:
        return None

    return (audio * min(0.9 / peak, 25.0)).astype("float32")


def clean_text(text):
    """
    Tidy a transcript: Sophia's name, no wake phrase, no punctuation
    left over, and nothing at all if it is a typical false phrase.
    """

    text = text.strip()

    for pattern, replacement in NAME_FIXES:
        text = pattern.sub(replacement, text)

    text = WAKE_PREFIX.sub("", text).strip()

    if text.lower().strip(" .!?,") in HALLUCINATIONS:
        return ""

    return text


def mentions(text, names, cutoff=0.66):
    """
    Is one of `names` in `text`, allowing for how a recognizer mishears
    it? ("Hey Travis" and "hey jervis" both count for Jarvis.)
    """

    import difflib

    words = re.findall(r"[a-z']+", text.lower())

    for name in names:

        for word in words:

            if difflib.SequenceMatcher(None, word, name.lower()).ratio() >= cutoff:
                return True

    return False


class Transcriber:
    """
    Local Whisper. The model loads the first time it is needed.
    """

    def __init__(self, model_name="base.en", model_factory=None):

        self.model_name = model_name
        self._model_factory = model_factory or self._load_model
        self._model = None

        # the model may be loaded by a background warm-up and by the
        # first request at the same time: only once
        self._load_lock = threading.Lock()

    @staticmethod
    def _load_model(name):

        from faster_whisper import WhisperModel

        return WhisperModel(
            name,
            device="cpu",
            compute_type="int8",
            cpu_threads=min(8, os.cpu_count() or 4),
        )

    def preload(self):
        """
        Load the speech model now (in the background at start-up), so the
        first spoken request does not wait for it.
        """

        self._ensure_model()

    def _ensure_model(self):

        with self._load_lock:

            if self._model is None:

                log.info("Loading speech model %s", self.model_name)
                self._model = self._model_factory(self.model_name)

        return self._model

    def hears(self, audio, names=("jarvis",)):
        """
        Does this short audio contain one of the names? Used to confirm
        the wake word: the words are compared loosely, because the
        recognizer may write "Jarvis" as "Travis", "Jarvas" or "Jervis".
        """

        text = self.transcribe_quick(audio)

        log.info("Wake word check heard: %r", text)

        return mentions(text, names)

    def transcribe_quick(self, audio):
        """
        A fast, plain transcription (no vocabulary hint, one beam) of a
        short clip.
        """

        audio = prepare_audio(audio)

        if audio is None:
            return ""

        segments, _ = self._ensure_model().transcribe(
            audio, language="en", beam_size=1, vad_filter=False,
            condition_on_previous_text=False,
        )

        return " ".join(segment.text.strip() for segment in segments)

    def transcribe(self, audio):
        """
        Audio (float32, 16 kHz mono) -> text. Empty audio -> "".
        """

        if audio is None or len(audio) < SAMPLE_RATE * 0.3:
            return ""

        audio = prepare_audio(audio)

        if audio is None:
            return ""

        segments, _ = self._ensure_model().transcribe(
            audio,
            language="en",
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 250},
            condition_on_previous_text=False,
            initial_prompt=VOCABULARY_HINT,
        )

        kept = []

        for segment in segments:

            # likely noise: Whisper itself is unsure it is speech
            if (
                getattr(segment, "no_speech_prob", 0.0) > 0.6
                and getattr(segment, "avg_logprob", 0.0) < -0.8
            ):
                continue

            kept.append(segment.text.strip())

        return clean_text(" ".join(kept))
