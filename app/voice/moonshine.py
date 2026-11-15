"""
Fast speech recognition for short voice commands: Moonshine, a small model
whose running time grows with how much you said (Whisper always works on a
30-second window, so even "open GitHub" took about 2 seconds on this PC;
Moonshine base takes about 1 second and Moonshine tiny about 0.3).

The inference loop below is a compact version of the reference code in
Useful Sensors' `moonshine` project (MIT licence), which runs the two
ONNX models (encoder, then a decoder that writes the words one by one).
The models and the tokenizer (a few hundred MB for base) download from
Hugging Face the first time and are cached.
"""

import logging
import threading
import time

import numpy as np

from app.voice.listener import (
    SAMPLE_RATE,
    clean_text,
    mentions,
    prepare_audio,
)

log = logging.getLogger("sophia.voice")

REPO = "UsefulSensors/moonshine"

# layers, key/value heads and head size of each model
SIZES = {
    "tiny": (6, 8, 36),
    "base": (8, 8, 52),
}

DECODER_START = 1
END_OF_TEXT = 2

# Moonshine writes about 6 words-pieces per second of speech; a limit a
# little above that stops a runaway repeat on strange audio
TOKENS_PER_SECOND = 6.5


class MoonshineModel:
    """
    encoder / decoder: ONNX Runtime sessions (anything with run() and
    get_inputs()); tokenizer: a tokenizers.Tokenizer.
    """

    def __init__(self, encoder, decoder, tokenizer, name="base"):

        self.encoder = encoder
        self.decoder = decoder
        self.tokenizer = tokenizer

        self.layers, self.heads, self.head_dim = SIZES[name]

        self._encoder_inputs = [i.name for i in encoder.get_inputs()]
        self._decoder_inputs = [i.name for i in decoder.get_inputs()]

    def generate(self, audio, max_tokens):
        """
        audio: float32, 16 kHz mono, shape (samples,). Returns the token ids.
        """

        batch = np.asarray(audio, dtype="float32")[None, :]
        mask = np.ones_like(batch, dtype="int64")

        inputs = {"input_values": batch}

        if "attention_mask" in self._encoder_inputs:
            inputs["attention_mask"] = mask

        hidden = self.encoder.run(None, inputs)[0]

        cache = {
            f"past_key_values.{layer}.{kind}.{part}": np.zeros(
                (0, self.heads, 1, self.head_dim), dtype="float32"
            )
            for layer in range(self.layers)
            for kind in ("decoder", "encoder")
            for part in ("key", "value")
        }

        tokens = [DECODER_START]
        current = [[DECODER_START]]

        for step in range(max_tokens):

            use_cache = step > 0

            feed = {
                "input_ids": current,
                "encoder_hidden_states": hidden,
                "use_cache_branch": [use_cache],
                **cache,
            }

            if "encoder_attention_mask" in self._decoder_inputs:
                feed["encoder_attention_mask"] = mask

            logits, *present = self.decoder.run(None, feed)

            token = int(logits[0, -1].argmax())

            tokens.append(token)

            if token == END_OF_TEXT:
                break

            current = [[token]]

            for key, value in zip(cache.keys(), present):

                # the encoder's cache is computed once; the decoder's grows
                if not use_cache or "decoder" in key:
                    cache[key] = value

        return tokens

    def recognize(self, audio):
        """
        Audio -> text.
        """

        seconds = len(audio) / SAMPLE_RATE

        limit = max(8, int(seconds * TOKENS_PER_SECOND) + 4)

        tokens = self.generate(audio, limit)

        return self.tokenizer.decode(tokens, skip_special_tokens=True).strip()


def is_runaway(text):
    """
    Did the decoder get stuck repeating itself ("the the the the")?
    """

    words = text.lower().split()

    if len(words) < 6:
        return False

    return len(set(words)) <= max(1, len(words) // 5)


def load_moonshine(name="base"):
    """
    Download (the first time) and load a Moonshine model.
    """

    import onnxruntime
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    folder = f"onnx/merged/{name}/float"

    def fetch(filename, subfolder):
        """
        The cached file when it is there (no network, no delay), otherwise
        download it.
        """

        try:
            return hf_hub_download(REPO, filename, subfolder=subfolder, local_files_only=True)

        except Exception:
            return hf_hub_download(REPO, filename, subfolder=subfolder)

    paths = {
        part: fetch(f"{part}.onnx", folder)
        for part in ("encoder_model", "decoder_model_merged")
    }

    tokenizer = Tokenizer.from_file(fetch("tokenizer.json", "onnx/merged/base/float"))

    import os

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = min(8, os.cpu_count() or 4)

    sessions = {
        part: onnxruntime.InferenceSession(path, sess_options=options)
        for part, path in paths.items()
    }

    return MoonshineModel(
        sessions["encoder_model"], sessions["decoder_model_merged"], tokenizer, name
    )


class MoonshineTranscriber:
    """
    The same interface as the Whisper Transcriber (preload, transcribe,
    hears), so either can be used.
    """

    def __init__(self, name="base", model_factory=load_moonshine):

        self.name = name
        self._factory = model_factory
        self._model = None
        self._lock = threading.Lock()

    def preload(self):

        self._ensure_model()

    def _ensure_model(self):

        with self._lock:

            if self._model is None:

                log.info("Loading Moonshine %s", self.name)

                started = time.monotonic()

                self._model = self._factory(self.name)

                log.info("Moonshine %s loaded in %.1f s", self.name, time.monotonic() - started)

        return self._model

    def _recognize(self, audio):

        audio = prepare_audio(audio)

        if audio is None:
            return ""

        text = self._ensure_model().recognize(audio)

        return "" if is_runaway(text) else text

    def transcribe(self, audio):
        """
        Audio (float32, 16 kHz mono) -> cleaned text. Empty audio -> "".
        """

        if audio is None or len(audio) < SAMPLE_RATE * 0.3:
            return ""

        started = time.monotonic()

        text = clean_text(self._recognize(audio))

        log.info(
            "Heard %r (%.1f s of speech, loudest %.3f, recognized in %.2f s, Moonshine %s)",
            text, len(audio) / SAMPLE_RATE, float(np.max(np.abs(audio))),
            time.monotonic() - started, self.name,
        )

        return text

    def hears(self, audio, names=("sophia",), cutoff=0.66):
        """
        Does this short clip contain one of the names? (Wake word check.)
        """

        started = time.monotonic()

        text = self._recognize(audio)

        log.info(
            "Wake word check heard: %r (%.2f s, Moonshine %s)",
            text, time.monotonic() - started, self.name,
        )

        return mentions(text, names, cutoff)


class FallbackTranscriber:
    """
    Uses the fast recognizer; if it cannot load or fails (for example no
    internet for the first download), Whisper takes over.
    """

    # A clip this long and this loud had speech in it: if the fast
    # recognizer wrote nothing, the slower one is asked
    MIN_SPEECH_SECONDS = 0.6
    MIN_SPEECH_PEAK = 0.02

    def __init__(self, primary, secondary, samples_folder=None):

        self.primary = primary
        self.secondary = secondary
        self.samples_folder = samples_folder

        self._primary_broken = False

    def _use(self, method, *args):

        if not self._primary_broken:

            try:
                return getattr(self.primary, method)(*args)

            except Exception as e:

                self._primary_broken = True

                log.warning("The fast speech recognizer failed (%s); using Whisper", e)

        return getattr(self.secondary, method)(*args)

    def preload(self):

        try:
            self.primary.preload()

        except Exception as e:

            self._primary_broken = True

            log.warning("The fast speech recognizer could not load (%s); using Whisper", e)

            self.secondary.preload()

    def _had_speech(self, audio):

        if audio is None or len(audio) < SAMPLE_RATE * self.MIN_SPEECH_SECONDS:
            return False

        centred = np.asarray(audio, dtype="float32") - float(np.mean(audio))

        return float(np.max(np.abs(centred))) >= self.MIN_SPEECH_PEAK

    def transcribe(self, audio):

        text = self._use("transcribe", audio)

        engine = "fast" if not self._primary_broken else "whisper"

        # never lose a command: nothing heard in a clip that clearly held
        # speech is worth a second opinion
        if not text and not self._primary_broken and self._had_speech(audio):

            log.info("The fast recognizer heard nothing in a clip with speech; asking Whisper")

            try:

                text = self.secondary.transcribe(audio)

                engine = "whisper (second opinion)"

            except Exception as e:
                log.warning("Whisper could not help either: %s", e)

        if self.samples_folder is not None and audio is not None and len(audio):

            from app.voice.voicelog import save_sample

            save_sample(audio, text, self.samples_folder, engine)

        return text

    def hears(self, audio, names=("sophia",), cutoff=0.66):

        return self._use("hears", audio, names, cutoff)
