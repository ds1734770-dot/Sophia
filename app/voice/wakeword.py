"""
Hands-free activation: listens to the microphone for the wake phrase
("Hey Sophia") and calls on_wake() when it hears it. Audio never leaves
the computer.

Two kinds of wake model:

- "hey_sophia" (the default): SpeechWakeModel notices speech by its
  loudness, and the local Whisper recognizer (MIT, already used for
  requests) checks whether it said the name. Whisper base heard "Hey
  Sophia" in every test clip and ignored "sofa", "Sophie" and "so far";
  the small Moonshine models often return nothing for such a short clip,
  so they are not used for this. No extra model to download, and nothing
  with a non-commercial license.
- an openWakeWord model by name ("hey_jarvis", "alexa", "hey_mycroft"):
  a dedicated keyword model, with the recognizer confirming weak matches.
  openWakeWord's pre-trained models are CC BY-NC-SA 4.0 (non-commercial).

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
STALL_SECONDS = 8.0
RESTART_BACKOFF = (1.0, 3.0, 8.0, 20.0)

RING_SECONDS = 4.0
NOISE_WINDOW_BLOCKS = 150        # about 12 seconds

DEFAULT_WAKE_WORD = "hey_sophia"

# Wake phrases spotted by speech recognition instead of a keyword model,
# with the names the recognizer must hear
# (both spellings Whisper writes; with SPEECH_NAME_CUTOFF only near-exact
# words count, so "sofa" and "Sophie" do not)
SPEECH_WAKE_WORDS = {
    "hey_sophia": ("sophia", "sofia"),
    "sophia": ("sophia", "sofia"),
}

# How closely a word must match one of the names: "sophia" and "sofia"
# count, "sofa" (0.89 like "sofia") and "Sophie" (0.83) do not
SPEECH_NAME_CUTOFF = 0.92

# SpeechWakeModel: what counts as speech, and when to check it
SPEECH_MIN_LEVEL = 0.010             # RMS of float audio; quieter is never speech
SPEECH_OVER_NOISE = 3.0              # or this many times the room's noise
SPEECH_MIN_SECONDS = 0.30            # shorter sounds are clicks and knocks
SPEECH_END_SECONDS = 0.30            # this much quiet ends a phrase
SPEECH_RECHECK_SECONDS = 1.4         # while someone keeps talking

# A score at or above the threshold wakes Sophia at once. A weaker score
# (this fraction of the threshold or more) counts when it holds for
# CONFIRM_BLOCKS blocks in a row: real speech of the wake word often peaks
# a little under the threshold, but noise rarely repeats.
WEAK_FACTOR = 0.66
CONFIRM_BLOCKS = 2

# how often a near miss is written to the log
NEAR_MISS_LOG_SECONDS = 2.0
NEAR_MISS_SCORE = 0.2

# A score this fraction of the threshold or more is "something like the
# wake word": the speech recognizer is asked to confirm that the last
# seconds really contained the name (see WakeWordListener.verifier).
VERIFY_FACTOR = 0.36
VERIFY_GAP_SECONDS = 1.5
VERIFY_DELAY_SECONDS = 0.55          # let the end of the phrase arrive
VERIFY_WINDOW_SECONDS = 2.6          # how much audio before it to check


def wake_decision(score, threshold, streak):
    """
    (wake now?, new streak of weak scores)
    """

    if score >= threshold:
        return True, 0

    if score >= threshold * WEAK_FACTOR:

        streak += 1

        return streak >= CONFIRM_BLOCKS, streak

    return False, 0


def spoken_name(model):

    return model.replace("_", " ").title()


def wake_names(word):
    """
    The words the speech recognizer must hear for this wake word.
    """

    if word in SPEECH_WAKE_WORDS:
        return SPEECH_WAKE_WORDS[word]

    return (word.split("_")[-1],)


class SpeechWakeModel:
    """
    Finds moments worth checking for the wake phrase: someone started or
    finished saying something. predict() returns {word: 1.0} at such a
    moment and {word: 0.0} otherwise; the listener then asks the speech
    recognizer whether the name was said (verify_only).
    """

    verify_only = True

    def __init__(self, word=DEFAULT_WAKE_WORD, block_seconds=None):

        self.word = word
        self.block_seconds = block_seconds or BLOCK / SAMPLE_RATE

        self.reset()

    def reset(self):

        self._noise = 0.004
        self._speech = 0.0          # seconds of the current phrase
        self._quiet = 0.0           # seconds of quiet since it
        self._since_check = 0.0

    def level_is_speech(self, level):

        return level >= max(SPEECH_MIN_LEVEL, self._noise * SPEECH_OVER_NOISE)

    def predict(self, chunk):

        samples = np.asarray(chunk, dtype="float32")

        if np.asarray(chunk).dtype == np.int16:
            samples = samples / 32768.0

        level = float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0.0

        step = self.block_seconds
        check = False

        if self.level_is_speech(level):

            self._speech += step
            self._quiet = 0.0
            self._since_check += step

            # long phrase ("Hey Sophia, open YouTube"): check as it goes
            if self._speech >= SPEECH_MIN_SECONDS * 2 and self._since_check >= SPEECH_RECHECK_SECONDS:
                check = True

        else:

            # the room's noise follows the quiet parts only
            self._noise = 0.95 * self._noise + 0.05 * level

            if self._speech > 0:

                self._quiet += step

                if self._quiet >= SPEECH_END_SECONDS:

                    # the phrase has ended: check it unless it was a click
                    # or was just checked
                    check = self._speech >= SPEECH_MIN_SECONDS and self._since_check >= 0.5

                    self._speech = 0.0
                    self._quiet = 0.0

        if check:
            self._since_check = 0.0

        return {self.word: 1.0 if check else 0.0}


def load_wake_model(name):
    """
    The wake model: the speech-based one for "hey_sophia", otherwise the
    openWakeWord model of that name (its small file downloads on first use).
    """

    if name in SPEECH_WAKE_WORDS:
        return SpeechWakeModel(name)

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
        verifier=None,
        on_started=None,
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
        self._streak = 0
        self._last_near_miss = -NEAR_MISS_LOG_SECONDS

        # verifier(audio) -> bool: does this audio really say the name?
        # Used for scores that are only a little like the wake word.
        self.verifier = verifier
        self.on_started = on_started
        self._verifying = False
        self._last_verify = -VERIFY_GAP_SECONDS

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

        began = time.monotonic()

        self._model = self._model_factory(self.word)

        if getattr(self._model, "verify_only", False) and self.verifier is None:
            raise RuntimeError(f"The wake phrase '{self.word}' needs the speech recognizer")

        loaded = time.monotonic()

        self._open_stream()

        log.info(
            "Wake word start-up: model %.1f s, microphone %.1f s",
            loaded - began, time.monotonic() - loaded,
        )

        self.running = True

        self._thread = threading.Thread(
            target=self._run, name="wake-word", daemon=True
        )

        self._thread.start()

        log.info("Listening for the wake word '%s'", self.word)

        if self.on_started is not None:

            try:
                self.on_started()

            except Exception:
                log.exception("on_started failed")

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

        # speech-based wake phrase: every candidate is checked by the
        # recognizer, and nothing wakes Sophia without that check
        if getattr(self._model, "verify_only", False):

            if (
                score > 0
                and not self._verifying
                and now - self._last_wake >= COOLDOWN_SECONDS
            ):

                self._last_verify = now
                self._verifying = True

                threading.Thread(
                    target=self._verify, args=(now, score), name="wake-verify", daemon=True
                ).start()

            return

        wake, self._streak = wake_decision(score, self.threshold, self._streak)

        if not wake and score >= NEAR_MISS_SCORE and now - self._last_near_miss >= NEAR_MISS_LOG_SECONDS:

            # so a "it never hears me" report can be checked in the log
            self._last_near_miss = now

            log.info("Wake word: heard something (score %.2f, needs %.2f)", score, self.threshold)

        if wake:

            self._trigger(now, score, "model")

        elif (
            self.verifier is not None
            and not self._verifying
            and score >= self.threshold * VERIFY_FACTOR
            and now - self._last_verify >= VERIFY_GAP_SECONDS
            and now - self._last_wake >= COOLDOWN_SECONDS
        ):

            self._last_verify = now
            self._verifying = True

            threading.Thread(
                target=self._verify, args=(now, score), name="wake-verify", daemon=True
            ).start()

    def _trigger(self, now, score, how):
        """
        Wake Sophia (once per cooldown).
        """

        if now - self._last_wake < COOLDOWN_SECONDS:
            return

        self._streak = 0
        self._last_wake = now
        self.last_wake_time = now

        log.info("Wake word heard (score %.2f, %s)", score, how)

        # the callback may be slow (it opens the recorder): do not
        # block the audio worker
        threading.Thread(target=self.on_wake, daemon=True).start()

    def _verify(self, stamp, score):
        """
        The model heard something like the wake word: let the speech
        recognizer decide whether it really was the name.
        """

        try:

            time.sleep(VERIFY_DELAY_SECONDS)

            audio = self.audio_since(stamp - VERIFY_WINDOW_SECONDS)

            if len(audio) < SAMPLE_RATE * 0.5:

                log.info("Wake word: possible (score %.2f), but too little audio to check", score)

                return

            started = time.monotonic()

            heard = bool(self.verifier(audio))

            log.info(
                "Wake word: possible (score %.2f), speech check %s (%.1f s)",
                score, "confirmed it" if heard else "did not hear the name",
                time.monotonic() - started,
            )

            if heard and not self._paused and self.running:
                self._trigger(stamp, score, "confirmed by speech")

        except Exception:

            log.exception("Wake word verification failed")

        finally:

            self._verifying = False
