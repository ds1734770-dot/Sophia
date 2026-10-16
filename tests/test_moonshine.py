import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.voice.listener import clean_text
from app.voice.moonshine import (
    FallbackTranscriber,
    MoonshineModel,
    MoonshineTranscriber,
    is_runaway,
)

RATE = 16000


def tone(seconds=1.0, amplitude=0.3):

    t = np.arange(int(seconds * RATE)) / RATE

    return (np.sin(2 * np.pi * 220 * t) * amplitude).astype("float32")


# ---------------------------------------------------------------
# The inference loop (with fake ONNX sessions)
# ---------------------------------------------------------------

class FakeEncoder:

    def __init__(self, with_mask=True):

        self.with_mask = with_mask
        self.inputs = []

    def get_inputs(self):

        names = ["input_values"] + (["attention_mask"] if self.with_mask else [])

        return [SimpleNamespace(name=n) for n in names]

    def run(self, outputs, feed):

        self.inputs.append(feed)

        return [np.zeros((1, 4, 8), dtype="float32")]


class FakeDecoder:
    """
    Says the tokens in `say` one by one, then the end token.
    """

    def __init__(self, say):

        self.say = list(say)
        self.calls = []

        self.layers = 2
        self.step = 0

    def get_inputs(self):

        names = ["input_ids", "encoder_hidden_states", "use_cache_branch", "encoder_attention_mask"]
        names += [
            f"past_key_values.{i}.{kind}.{part}"
            for i in range(6) for kind in ("decoder", "encoder") for part in ("key", "value")
        ]

        return [SimpleNamespace(name=n) for n in names]

    def run(self, outputs, feed):

        self.calls.append(feed)

        # a new sentence starts when the cache is built again
        if feed["use_cache_branch"] == [False]:
            self.step = 0

        step = self.step

        self.step += 1

        token = self.say[step] if step < len(self.say) else 2

        logits = np.zeros((1, 1, 10), dtype="float32")
        logits[0, 0, token] = 5.0

        # one new cache entry per input cache, tagged with the step
        present = [
            np.full((step + 1, 8, 1, 36), step, dtype="float32") for _ in range(24)
        ]

        return [logits] + present


class FakeTokenizer:

    def decode(self, tokens, skip_special_tokens=True):

        assert skip_special_tokens

        words = {3: "open", 4: "GitHub", 5: "now"}

        return " ".join(words[t] for t in tokens if t in words)


def make_model(say, with_mask=True):

    return MoonshineModel(FakeEncoder(with_mask), FakeDecoder(say), FakeTokenizer(), "tiny")


def test_the_decoder_writes_tokens_until_the_end_marker():

    model = make_model([3, 4])

    tokens = model.generate(tone(1), max_tokens=20)

    assert tokens == [1, 3, 4, 2]
    assert model.recognize(tone(1)) == "open GitHub"


def test_the_first_step_builds_the_cache_and_later_steps_reuse_it():

    model = make_model([3, 4, 5])

    model.generate(tone(1), max_tokens=20)

    first, second, third = model.decoder.calls[:3]

    assert first["use_cache_branch"] == [False] and second["use_cache_branch"] == [True]
    assert first["input_ids"] == [[1]] and second["input_ids"] == [[3]] and third["input_ids"] == [[4]]

    # the decoder's cache grows from step to step, the encoder's stays as first computed
    assert second["past_key_values.0.decoder.key"][0, 0, 0, 0] == 0
    assert third["past_key_values.0.decoder.key"][0, 0, 0, 0] == 1
    assert second["past_key_values.0.encoder.key"].shape == third["past_key_values.0.encoder.key"].shape == (1, 8, 1, 36)


def test_the_attention_mask_is_sent_only_when_the_model_wants_it():

    with_mask = make_model([3])
    without = make_model([3], with_mask=False)

    with_mask.generate(tone(1), 5)
    without.generate(tone(1), 5)

    assert "attention_mask" in with_mask.encoder.inputs[0]
    assert "attention_mask" not in without.encoder.inputs[0]


def test_a_decoder_that_never_stops_is_cut_off():

    model = make_model([3] * 100)

    assert len(model.generate(tone(1), max_tokens=7)) == 8          # start token + 7


def test_the_length_limit_follows_how_long_the_clip_is():

    model = make_model([3] * 500)

    short = model.recognize(tone(1.0))
    long = model.recognize(tone(4.0))

    assert len(long.split()) > len(short.split())
    assert len(short.split()) <= 6.5 + 4


@pytest.mark.parametrize("text,expected", [
    ("the the the the the the the the", True),
    ("open GitHub", False),
    ("open the browser and search for the weather", False),
    ("", False),
])
def test_a_stuck_decoder_is_recognised(text, expected):

    assert is_runaway(text) is expected


# ---------------------------------------------------------------
# The transcriber
# ---------------------------------------------------------------

class StubModel:

    def __init__(self, text):
        self.text = text
        self.heard = []

    def recognize(self, audio):
        self.heard.append(len(audio))
        return self.text


def transcriber(text, loads=None):

    def factory(name):

        if loads is not None:
            loads.append(name)

        return StubModel(text)

    return MoonshineTranscriber("base", model_factory=factory)


def test_a_command_is_cleaned_like_the_whisper_one():

    assert transcriber("Hey Jarvis, open git hub").transcribe(tone(2)) == "open GitHub"
    assert transcriber("what is the weather").transcribe(tone(2)) == "what is the weather"


def test_silence_and_tiny_clips_are_not_recognised():

    stub = transcriber("hallucination")

    assert stub.transcribe(np.zeros(RATE, dtype="float32")) == ""
    assert stub.transcribe(tone(0.1)) == ""
    assert stub.transcribe(None) == ""
    assert stub._model is None                         # never even loaded


def test_a_false_phrase_or_runaway_is_dropped():

    assert transcriber("Thank you.").transcribe(tone(2)) == ""
    assert transcriber("go go go go go go go go go").transcribe(tone(2)) == ""


def test_the_model_loads_once():

    loads = []

    t = transcriber("open GitHub", loads)

    t.preload()
    t.transcribe(tone(2))
    t.transcribe(tone(2))

    assert loads == ["base"]


def test_the_wake_word_check_listens_for_the_name_and_logs_the_time(caplog):

    with caplog.at_level(logging.INFO, logger="sophia.voice"):

        assert transcriber("Hey Travis").hears(tone(2), ("jarvis",))
        assert not transcriber("Can you do this").hears(tone(2), ("jarvis",))

    assert "Wake word check heard: 'Hey Travis'" in caplog.text


def test_recognition_time_is_logged(caplog):

    with caplog.at_level(logging.INFO, logger="sophia.voice"):
        transcriber("open GitHub").transcribe(tone(2))

    assert "Heard 'open GitHub'" in caplog.text and "Moonshine base" in caplog.text


# ---------------------------------------------------------------
# Falling back to Whisper
# ---------------------------------------------------------------

class Primary:

    def __init__(self, fail_load=False, fail_run=False):
        self.fail_load = fail_load
        self.fail_run = fail_run
        self.calls = 0

    def preload(self):
        if self.fail_load:
            raise OSError("no internet for the download")

    def transcribe(self, audio):
        self.calls += 1
        if self.fail_run:
            raise RuntimeError("boom")
        return "fast"

    def hears(self, audio, names):
        return True


class Secondary:

    def __init__(self):
        self.loaded = 0

    def preload(self):
        self.loaded += 1

    def transcribe(self, audio):
        return "whisper"

    def hears(self, audio, names):
        return False


def test_the_fast_recognizer_is_used_when_it_works():

    t = FallbackTranscriber(Primary(), Secondary())

    t.preload()

    assert t.transcribe(tone()) == "fast" and t.hears(tone(), ("jarvis",)) is True
    assert t.secondary.loaded == 0                     # Whisper stays unloaded


def test_whisper_takes_over_when_the_fast_one_cannot_load():

    t = FallbackTranscriber(Primary(fail_load=True), Secondary())

    t.preload()

    assert t.secondary.loaded == 1 and t.transcribe(tone()) == "whisper"
    assert t.primary.calls == 0                        # not tried again


def test_whisper_takes_over_after_a_failure_and_stays():

    primary = Primary(fail_run=True)
    t = FallbackTranscriber(primary, Secondary())

    assert t.transcribe(tone()) == "whisper"
    assert t.transcribe(tone()) == "whisper" and primary.calls == 1


# ---------------------------------------------------------------
# Spoken names are put back together
# ---------------------------------------------------------------

@pytest.mark.parametrize("said,expected", [
    ("open git hub", "open GitHub"),
    ("Open Github.", "Open GitHub."),
    ("play it on you tube", "play it on YouTube"),
    ("open your tube and play music", "open YouTube and play music"),
    ("open note pad", "open Notepad"),
    ("message him on whats app", "message him on WhatsApp"),
    ("open power point", "open PowerPoint"),
    ("ask chat gpt", "ask ChatGPT"),
    ("open v s code", "open VS Code"),
    ("open the github", "open the GitHub"),
])
def test_program_names_are_put_back_together(said, expected):

    assert clean_text(said) == expected


# ---------------------------------------------------------------
# The real model (skipped when it is not downloaded)
# ---------------------------------------------------------------

def cached(name):

    try:

        from huggingface_hub import try_to_load_from_cache

        return all(
            isinstance(
                try_to_load_from_cache("UsefulSensors/moonshine", f"{part}.onnx", subfolder=f"onnx/merged/{name}/float"),
                str,
            )
            for part in ("encoder_model", "decoder_model_merged")
        )

    except Exception:
        return False


@pytest.mark.skipif(not cached("tiny"), reason="Moonshine tiny is not downloaded")
def test_the_real_model_hears_a_spoken_command():

    voice_file = Path("data/models/piper/en_GB-jenny_dioco-medium.onnx")

    if not voice_file.exists():
        pytest.skip("no Piper voice to make test speech with")

    from piper import PiperVoice

    voice = PiperVoice.load(voice_file)

    speech = np.concatenate([c.audio_float_array for c in voice.synthesize("Hey Jarvis, open GitHub.")])

    speech = np.interp(
        np.linspace(0, len(speech), int(len(speech) * RATE / 22050)), np.arange(len(speech)), speech
    ).astype("float32")

    real = MoonshineTranscriber("tiny")

    text = real.transcribe(speech)

    assert "github" in text.lower()
    assert real.hears(speech, ("jarvis",))
