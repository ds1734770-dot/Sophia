"""
"Hey Sophia": the speech-based wake phrase (no keyword model).
"""

import numpy as np

from app.voice.listener import mentions
from app.voice.wakeword import (
    BLOCK,
    SAMPLE_RATE,
    SPEECH_NAME_CUTOFF,
    SPEECH_WAKE_WORDS,
    SpeechWakeModel,
    WakeWordListener,
    load_wake_model,
    wake_names,
)

NAMES = SPEECH_WAKE_WORDS["hey_sophia"]


def blocks(level, seconds):
    """
    int16 blocks of a steady tone at `level` (0 to 1).
    """

    count = int(seconds * SAMPLE_RATE / BLOCK)
    t = np.arange(BLOCK) / SAMPLE_RATE
    tone = (np.sin(2 * np.pi * 220 * t) * level * np.sqrt(2) * 32767).astype(np.int16)

    return [tone] * count


def candidates(model, chunks):

    return [i for i, chunk in enumerate(chunks) if model.predict(chunk)["hey_sophia"] > 0]


def test_hey_sophia_is_the_default_and_needs_no_keyword_model():

    from app.config.settings import DEFAULT_WAKE_WORD

    assert DEFAULT_WAKE_WORD == "hey_sophia"
    assert isinstance(load_wake_model("hey_sophia"), SpeechWakeModel)
    assert wake_names("hey_sophia") == NAMES
    assert wake_names("hey_jarvis") == ("jarvis",)


def test_a_short_phrase_is_checked_once_when_it_ends():

    model = SpeechWakeModel()

    chunks = blocks(0.001, 1.0) + blocks(0.1, 0.8) + blocks(0.001, 1.0)

    found = candidates(model, chunks)

    assert len(found) == 1
    # just after the phrase ended
    assert int(1.8 * SAMPLE_RATE / BLOCK) <= found[0] <= int(2.3 * SAMPLE_RATE / BLOCK)


def test_clicks_and_silence_are_never_checked():

    model = SpeechWakeModel()

    chunks = blocks(0.001, 1.0) + blocks(0.2, 0.08) + blocks(0.001, 2.0)

    assert candidates(model, chunks) == []


def test_a_long_phrase_is_checked_while_it_goes_on():

    model = SpeechWakeModel()

    found = candidates(model, blocks(0.001, 0.5) + blocks(0.1, 4.0) + blocks(0.001, 1.0))

    assert len(found) >= 3


def test_steady_room_noise_becomes_the_baseline():

    model = SpeechWakeModel()

    # a loud but steady fan: the noise floor rises with it
    for chunk in blocks(0.008, 5.0):
        model.predict(chunk)

    assert not model.level_is_speech(0.009)
    assert model.level_is_speech(0.05)


def test_name_matching_is_strict():

    for text in ("Hey Sophia!", "Hey Sofia.", "Sophia, what time is it?", "Is that Sophia's?"):
        assert mentions(text, NAMES, SPEECH_NAME_CUTOFF), text

    for text in ("Hey sofa.", "I bought a new sofa", "Sophie is here", "So far so good", "Hey Soka"):
        assert not mentions(text, NAMES, SPEECH_NAME_CUTOFF), text


class Stream:

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass


def test_only_the_recognizer_can_wake_sophia(monkeypatch):

    import time

    clock = [0.0]
    woke = []
    heard = []

    def verifier(audio):
        heard.append(len(audio))
        return len(heard) >= 2

    monkeypatch.setattr("app.voice.wakeword.VERIFY_DELAY_SECONDS", 0)

    listener = WakeWordListener(
        lambda: woke.append(1), word="hey_sophia", clock=lambda: clock[0], verifier=verifier,
    )

    listener._model = load_wake_model("hey_sophia")
    listener.running = True

    def phrase():

        for chunk in blocks(0.001, 0.5) + blocks(0.1, 0.8) + blocks(0.001, 0.6):
            clock[0] += BLOCK / SAMPLE_RATE
            listener._process(clock[0], chunk)

        deadline = time.time() + 5

        while (listener._verifying or not heard) and time.time() < deadline:
            time.sleep(0.01)

        time.sleep(0.05)

    phrase()
    assert len(heard) == 1 and not woke     # the recognizer said no

    clock[0] += 5
    phrase()
    assert len(woke) == 1                   # the recognizer heard the name

    listener.running = False


def test_speech_wake_word_refuses_to_start_without_a_recognizer():

    import pytest

    listener = WakeWordListener(lambda: None, word="hey_sophia", stream_factory=lambda cb: Stream())

    with pytest.raises(RuntimeError):
        listener.start()
