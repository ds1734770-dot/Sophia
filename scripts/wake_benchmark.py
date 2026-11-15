"""
Reproducible check of the "Hey Sophia" wake phrase (macOS).

Speaks wake phrases and look-alike phrases with several of macOS's own
voices (`say`), plays each through the real listener in real time with
background noise, and counts detections and false wakes.

    python scripts/wake_benchmark.py
    python scripts/wake_benchmark.py --voices Samantha,Daniel --model small.en

Synthetic voices are cleaner than a real microphone in a room, so treat
the numbers as a regression check, not as real-world accuracy.
"""

import argparse
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.voice.listener import Transcriber  # noqa: E402
from app.voice.wakeword import (  # noqa: E402
    BLOCK,
    SAMPLE_RATE,
    SPEECH_NAME_CUTOFF,
    SPEECH_WAKE_WORDS,
    WakeWordListener,
    load_wake_model,
)

WAKE = ["Hey Sophia", "Sophia", "Hey Sophia, open YouTube", "Sophia, what time is it"]

NOT_WAKE = [
    "Hey, what is the weather today", "I bought a new sofa yesterday", "Open the folder please",
    "Hey, can you help me", "So far so good", "Sofa", "Hey sofa", "Show me the photos",
    "Sophie is coming over", "I am going to the office",
]

VOICES = ["Samantha", "Daniel", "Karen", "Moira", "Rishi", "Tessa"]


def speak(text, voice, folder):

    aiff = Path(folder) / "clip.aiff"
    wav = Path(folder) / "clip.wav"

    subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)], check=True)

    with wave.open(str(wav)) as f:
        return np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)


def wakes(audio, verifier, seed):
    """
    Play one clip (with 1.5 s of room noise around it) through the
    listener in real time. True if Sophia woke.
    """

    rng = np.random.default_rng(seed)

    def noise(seconds):
        return rng.normal(0, 60, int(seconds * SAMPLE_RATE)).astype(np.int16)

    audio = np.concatenate([noise(1.5), audio, noise(1.5)])

    woke = []
    clock = [0.0]

    listener = WakeWordListener(lambda: woke.append(1), word="hey_sophia", clock=lambda: clock[0], verifier=verifier)
    listener._model = load_wake_model("hey_sophia")
    listener.running = True

    started = time.time()

    for i in range(0, len(audio) - BLOCK, BLOCK):

        clock[0] += BLOCK / SAMPLE_RATE

        listener._process(clock[0], audio[i:i + BLOCK])

        time.sleep(max(0.0, clock[0] - (time.time() - started)))

    while listener._verifying:
        time.sleep(0.05)

    return bool(woke)


def main(argv=None):

    if sys.platform != "darwin":
        print("This benchmark uses macOS's `say` voices.")
        return 1

    parser = argparse.ArgumentParser()
    parser.add_argument("--voices", default=",".join(VOICES))
    parser.add_argument("--model", default="base.en", help="Whisper model that confirms the name")
    args = parser.parse_args(argv)

    whisper = Transcriber(args.model)
    whisper.preload()

    def verifier(audio):
        return whisper.hears(audio, SPEECH_WAKE_WORDS["hey_sophia"], SPEECH_NAME_CUTOFF)

    hits = misses = false_wakes = quiet = 0

    with tempfile.TemporaryDirectory() as folder:

        for voice in args.voices.split(","):

            for i, text in enumerate(WAKE + NOT_WAKE):

                try:
                    audio = speak(text, voice.strip(), folder)

                except subprocess.CalledProcessError:
                    print(f"(voice {voice} is not installed; skipped)")
                    break

                woke = wakes(audio, verifier, seed=i)
                expected = text in WAKE

                if expected and woke:
                    hits += 1
                elif expected:
                    misses += 1
                    print(f"  missed      {voice:10} {text!r}")
                elif woke:
                    false_wakes += 1
                    print(f"  false wake  {voice:10} {text!r}")
                else:
                    quiet += 1

    print(f"\nWake phrases detected: {hits}/{hits + misses}")
    print(f"False wakes:           {false_wakes}/{false_wakes + quiet}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
