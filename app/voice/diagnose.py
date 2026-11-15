"""
Why doesn't the wake word work? Listen to the microphone exactly the way
Sophia does and show what it hears.

    python -m app.voice.diagnose              20 seconds on the default microphone
    python -m app.voice.diagnose --seconds 40
    python -m app.voice.diagnose --device 5   a particular input device (see --list)
    python -m app.voice.diagnose --list
    python -m app.voice.diagnose --word hey_jarvis   an openWakeWord model instead

For "Hey Sophia" (the default) it prints each phrase it noticed and what
the speech recognizer heard in it. For an openWakeWord model it shows,
every second, how loud you are and the model's score (0.50 or more is a
detection).
"""

import argparse
import sys
import time

import numpy as np

from app.voice.wakeword import (
    BLOCK,
    SAMPLE_RATE,
    SPEECH_WAKE_WORDS,
    THRESHOLD,
    SpeechWakeModel,
    load_wake_model,
    wake_decision,
    wake_names,
)


def list_devices():

    import sounddevice as sd

    default_in = sd.default.device[0]

    for index, device in enumerate(sd.query_devices()):

        if device["max_input_channels"] > 0:

            api = sd.query_hostapis(device["hostapi"])["name"]
            mark = " (default)" if index == default_in else ""

            print(f"{index:3d}  {device['name'][:60]!r:64} {device['default_samplerate']:.0f} Hz  {api}{mark}")


def bar(value, full, width=24):

    filled = int(min(1.0, value / full) * width)

    return "#" * filled + "." * (width - filled)


def run(seconds=20, device=None, word="hey_jarvis", threshold=THRESHOLD, out=sys.stdout):
    """
    An openWakeWord model: loudness and score every second. Returns a summary dict (peak level, best score, detections).
    """

    import sounddevice as sd

    model = load_wake_model(word)

    blocks = []

    def callback(data, frames, time_info, status):

        blocks.append((np.copy(data[:, 0]), str(status) if status else ""))

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="int16",
        blocksize=BLOCK, device=device, callback=callback,
    )

    info = sd.query_devices(device if device is not None else sd.default.device[0])

    print(f"Microphone: {info['name']}  (device native rate {info['default_samplerate']:.0f} Hz)", file=out)
    print(f"Say 'Hey Jarvis' now. Listening for {seconds} s...\n", file=out)
    print(f"{'sec':>3}  {'loudness':<26} {'level':>6}  {'wake score':<26} {'score':>5}", file=out)

    summary = {"peak": 0.0, "best": 0.0, "detections": 0, "status": set()}

    second_level = 0.0
    second_score = 0.0
    count = 0
    started = time.monotonic()
    shown = 0
    streak = 0
    second_woke = False

    stream.start()

    try:

        while time.monotonic() - started < seconds:

            time.sleep(0.04)

            while blocks:

                chunk, status = blocks.pop(0)

                if status:
                    summary["status"].add(status)

                level = float(np.sqrt(np.mean((chunk.astype("float32") / 32768.0) ** 2)))

                scores = model.predict(chunk)
                score = max(scores.values()) if scores else 0.0

                second_level = max(second_level, level)
                second_score = max(second_score, score)

                summary["peak"] = max(summary["peak"], level)
                summary["best"] = max(summary["best"], score)

                woke, streak = wake_decision(score, threshold, streak)

                if woke:

                    summary["detections"] += 1
                    second_woke = True
                    streak = 0

                count += 1

                # one line per second (12.5 blocks of 80 ms)
                if count >= 13:

                    shown += 1

                    flag = "  <-- WAKE" if second_woke else ""

                    print(
                        f"{shown:>3}  {bar(second_level, 0.1):<26} {second_level:6.3f}  "
                        f"{bar(second_score, 1.0):<26} {second_score:5.2f}{flag}",
                        file=out,
                    )

                    second_level = second_score = 0.0
                    second_woke = False
                    count = 0

    finally:

        stream.stop()
        stream.close()

    return summary


def run_speech(seconds=20, device=None, word="hey_sophia", out=sys.stdout):
    """
    "Hey Sophia": each phrase the loudness detector notices is passed to
    the speech recognizer, as in Sophia. Returns a summary dict.
    """

    import sounddevice as sd

    import os

    from app.voice.listener import Transcriber
    from app.voice.wakeword import SPEECH_NAME_CUTOFF

    model_name = os.getenv("WHISPER_MODEL") or "base.en"

    print(f"Loading the speech recognizer (Whisper {model_name})...", file=out)

    checker = Transcriber(model_name)
    checker.preload()

    names = wake_names(word)
    model = SpeechWakeModel(word)

    blocks = []

    def callback(data, frames, time_info, status):
        blocks.append((np.copy(data[:, 0]), str(status) if status else ""))

    summary = {"peak": 0.0, "best": 0.0, "detections": 0, "phrases": 0, "status": set()}
    history = []

    print(f"Say 'Hey Sophia' a few times. Listening for {seconds:.0f} s...\n", file=out)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=BLOCK,
                        device=device, callback=callback):

        ended = time.monotonic() + seconds

        while time.monotonic() < ended:

            time.sleep(0.05)

            while blocks:

                chunk, status = blocks.pop(0)

                if status:
                    summary["status"].add(status)

                audio = chunk.astype("float32") / 32768.0
                history.append(audio)
                history[:] = history[-int(3.2 * SAMPLE_RATE / BLOCK):]

                summary["peak"] = max(summary["peak"], float(np.abs(audio).max()))

                if model.predict(chunk)[word] > 0:

                    summary["phrases"] += 1

                    heard_text = checker.transcribe_quick(np.concatenate(history))

                    from app.voice.listener import mentions

                    heard = mentions(heard_text, names, SPEECH_NAME_CUTOFF)

                    if heard:
                        summary["detections"] += 1

                    mark = "  <-- WAKE" if heard else ""

                    print(f"  heard: {heard_text!r}{mark}", file=out)

    return summary


def speech_verdict(summary):

    if summary["detections"]:
        return (
            f"'Hey Sophia' was recognised {summary['detections']} time(s): the microphone and "
            "recognizer work. If Sophia still ignores you, check that hands-free is on."
        )

    if summary["peak"] < 0.02:
        return (
            f"The microphone is very quiet (peak {summary['peak']:.3f}). Check the input device and "
            "its level, and the microphone permission for the app that runs Sophia."
        )

    if not summary["phrases"]:
        return "No phrase was noticed. Speak a little louder, or move closer to the microphone."

    return (
        "Phrases were heard, but not the name. Say 'Hey Sophia' clearly with a short pause after "
        "it; the lines above show what the recognizer understood."
    )


def verdict(summary, threshold=THRESHOLD):
    """
    What the numbers mean, in plain words.
    """

    peak, best = summary["peak"], summary["best"]

    if summary["detections"]:
        return (
            f"The wake word was detected {summary['detections']} time(s), so the model and "
            "microphone work. If Sophia still ignores you, the problem is after detection."
        )

    if peak < 0.004:
        return (
            "The microphone is almost silent (nothing above 0.004). It is muted, covered, set to "
            "a very low input level, or Windows is using a different device. Check Settings > "
            "System > Sound > Input, and the laptop's microphone privacy switch."
        )

    if peak < 0.02:
        return (
            f"The microphone is very quiet (peak {peak:.3f}). Raise Input volume in Windows sound "
            "settings (and turn off 'Audio enhancements' if it is on), then try again."
        )

    if best >= 0.25:
        return (
            f"The model nearly caught it (best {best:.2f}, needs {threshold:.2f}). Lower "
            "WAKE_THRESHOLD (for example 0.3) or say it a little slower and clearer."
        )

    return (
        f"The microphone is loud enough (peak {peak:.3f}) but the model scored at most {best:.2f}. "
        "Either the audio is poor for it (a Bluetooth headset microphone, heavy noise "
        "suppression) or it did not hear the wake word as it expects."
    )


def main(argv=None):

    parser = argparse.ArgumentParser(prog="diagnose")
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    parser.add_argument("--word", default=None, help="wake word (default: WAKE_WORD or hey_sophia)")

    args = parser.parse_args(argv)

    if args.list:

        list_devices()

        return 0

    import os

    word = args.word or os.getenv("WAKE_WORD") or "hey_sophia"

    if word in SPEECH_WAKE_WORDS:

        summary = run_speech(args.seconds, args.device, word)

        print(f"\nLoudest: {summary['peak']:.3f}   phrases: {summary['phrases']}   wake: {summary['detections']}")
        print("\n" + speech_verdict(summary))

        return 0

    summary = run(args.seconds, args.device, word=word, threshold=args.threshold)

    print(f"\nLoudest: {summary['peak']:.3f}   best wake score: {summary['best']:.2f}   detections: {summary['detections']}")

    if summary["status"]:
        print("Audio warnings:", ", ".join(sorted(summary["status"])))

    print("\n" + verdict(summary, args.threshold))

    return 0


if __name__ == "__main__":

    sys.exit(main())
