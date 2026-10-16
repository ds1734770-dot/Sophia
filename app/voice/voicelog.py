"""
Keeps the last few voice requests on this PC (audio and what was
recognized) so a recognition problem can be investigated with the real
recording. Nothing leaves the computer; only the newest few are kept.
"""

import logging
import time
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger("sophia.voice")

KEEP = 12
SAMPLE_RATE = 16000


def save_sample(audio, text, folder, engine="", keep=KEEP, clock=time.time):
    """
    Write audio as a wav next to a .txt with the recognized text, and
    delete all but the newest `keep`. Never raises.
    """

    try:

        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)

        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(clock()))
        base = folder / stamp

        # two requests in the same second
        n = 1

        while base.with_suffix(".wav").exists():

            n += 1
            base = folder / f"{stamp}-{n}"

        pcm = (np.clip(np.asarray(audio, dtype="float32"), -1, 1) * 32767).astype("<i2")

        with wave.open(str(base.with_suffix(".wav")), "wb") as w:

            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm.tobytes())

        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0

        base.with_suffix(".txt").write_text(
            f"engine: {engine}\npeak: {peak:.4f}\nseconds: {len(audio) / SAMPLE_RATE:.1f}\ntext: {text}\n",
            encoding="utf-8",
        )

        old = sorted(folder.glob("*.wav"))[:-keep]

        for wav in old:

            wav.unlink(missing_ok=True)
            wav.with_suffix(".txt").unlink(missing_ok=True)

    except Exception:
        log.debug("Could not save the voice sample", exc_info=True)
