"""
Sound effects for the car, generated in code (no audio files): a flat-six
style engine that revs, a honk, a wiper swish, button clicks and two
chimes.

    python -m app.ui.sounds            play every sound once, in order
    python -m app.ui.sounds DIRECTORY  also save each one as a .wav file
"""

import logging
import sys
import threading
import time
import wave

import numpy as np

log = logging.getLogger("sophia.sound")

SAMPLE_RATE = 24000

CYLINDERS = 6


def _time(duration):

    return np.arange(int(duration * SAMPLE_RATE)) / SAMPLE_RATE


def _one_pole_lowpass(x, cutoff):
    """
    A simple low-pass filter (no scipy needed).
    """

    a = 1 - np.exp(-2 * np.pi * cutoff / SAMPLE_RATE)

    # exponential moving average through a convolution kernel
    length = int(min(len(x), 6 / a)) or 1

    kernel = a * (1 - a) ** np.arange(length)

    return np.convolve(x, kernel)[: len(x)]


def _fade(x, attack=0.01, release=0.05):

    n = len(x)

    a = min(n, int(attack * SAMPLE_RATE))
    r = min(n, int(release * SAMPLE_RATE))

    envelope = np.ones(n)

    if a:
        envelope[:a] = np.linspace(0, 1, a)

    if r:
        envelope[-r:] *= np.linspace(1, 0, r)

    return x * envelope


def _normalize(x, peak):

    top = float(np.max(np.abs(x))) or 1.0

    return (x / top * peak).astype("float32")


def engine(duration, rpm, level=0.5, rasp=0.5, seed=0):
    """
    An engine note. `rpm` is a function of normalised time (0 to 1) or
    a list of rpm values spread evenly over the duration. A flat-six
    fires three times per revolution.
    """

    t = _time(duration)
    u = t / duration

    if callable(rpm):

        revs = rpm(u)

    else:

        revs = np.interp(u, np.linspace(0, 1, len(rpm)), rpm)

    firing = revs / 60 * CYLINDERS / 2

    phase = 2 * np.pi * np.cumsum(firing) / SAMPLE_RATE

    wave_sum = np.zeros_like(t)

    # stacked harmonics give the throaty, buzzy tone
    for h in range(1, 13):
        wave_sum += np.sin(h * phase + 0.35 * h) / h ** (1.15 - 0.5 * rasp)

    # the uneven pulse of a boxer engine
    wave_sum *= 1 + 0.22 * np.sin(phase / 3 * 2)

    noise = np.random.default_rng(seed).normal(0, 1, len(t))

    exhaust = _one_pole_lowpass(noise, 1800) * (0.1 + 0.25 * rasp) * (revs / revs.max())

    sound = wave_sum + exhaust * 8

    sound = _one_pole_lowpass(sound, 2600 + 1.2 * float(revs.max()))

    return _normalize(sound, level)


def honk(level=0.4):
    """
    Two short beeps.
    """

    def beep(length):

        t = _time(length)

        tone = np.sin(2 * np.pi * 415 * t) + 0.8 * np.sin(2 * np.pi * 523 * t)
        tone += 0.3 * np.sign(np.sin(2 * np.pi * 415 * t))

        return _fade(tone, 0.008, 0.03)

    gap = np.zeros(int(0.07 * SAMPLE_RATE))

    return _normalize(np.concatenate([beep(0.16), gap, beep(0.22)]), level)


def click(level=0.25):

    t = _time(0.05)

    return _normalize(np.sin(2 * np.pi * 1900 * t) * np.exp(-t * 90), level)


def wiper(level=0.2, seed=1):
    """
    A soft rubber swish.
    """

    t = _time(0.55)

    noise = np.random.default_rng(seed).normal(0, 1, len(t))

    band = _one_pole_lowpass(noise, 3500) - _one_pole_lowpass(noise, 700)

    swish = band * np.sin(np.pi * t / t[-1]) ** 2

    return _normalize(swish, level)


def chime(notes, level=0.3):
    """
    Short bell-like notes played one after another.
    """

    parts = []

    for freq, length in notes:

        t = _time(length)

        tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2.01 * t)

        parts.append(_fade(tone * np.exp(-t * 6), 0.004, 0.02))

    return _normalize(np.concatenate(parts), level)


def render_all(volume=1.0):
    """
    Every sound as a dict {name: float32 samples}.
    """

    def revs_entry(u):
        return 2400 - 1500 * u ** 0.6

    entry = engine(1.3, revs_entry, 0.55 * volume)
    swell = np.sin(np.pi * _time(1.3) / 1.3) ** 0.8

    exit_curve = np.concatenate([
        np.linspace(1000, 4800, 500),
        np.linspace(3000, 6600, 850),
    ])

    exit_sound = engine(1.35, exit_curve, 0.7 * volume, rasp=0.8)
    u = _time(1.35) / 1.35
    exit_sound *= np.where(u < 0.37, 1.0, 1 - 0.95 * (u - 0.37) / 0.63)

    rendered = {
        "entry": (entry * swell).astype("float32"),
        "hover": _fade(engine(0.55, [1000, 2900, 1300], 0.4 * volume), 0.03, 0.15),
        "hide": _fade(engine(0.8, [1300, 3800], 0.5 * volume) * np.linspace(1, 0.05, int(0.8 * SAMPLE_RATE)), 0.02, 0.1),
        "exit": exit_sound.astype("float32"),
        "honk": honk(0.45 * volume),
        "click": click(0.3 * volume),
        "wiper": wiper(0.25 * volume),
        "listen": chime([(660, 0.1), (880, 0.16)], 0.3 * volume),
        "success": chime([(1320, 0.18), (1760, 0.3)], 0.28 * volume),
    }

    return {name: samples.astype("float32") for name, samples in rendered.items()}


class SoundMixer:
    """
    Plays the effects, several at once, through one output stream.
    Silent (and harmless) if there is no audio device.
    """

    def __init__(self, enabled=True, volume=0.6, stream_factory=None, sounds=None):

        self.enabled = enabled
        self.volume = max(0.0, min(1.0, volume))

        self._stream_factory = stream_factory or self._open_stream
        self._sounds = sounds

        self._voices = []
        self._lock = threading.Lock()
        self._stream = None
        self._failed = False

    @staticmethod
    def _open_stream(callback):

        import sounddevice as sd

        return sd.OutputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback
        )

    # ------------------------------------------------

    def play(self, name):
        """
        Start a sound (non-blocking). Unknown names are ignored.
        """

        if not self.enabled or self.volume <= 0 or self._failed:
            return

        if self._sounds is None:
            self._sounds = render_all()

        samples = self._sounds.get(name)

        if samples is None:
            return

        if not self._ensure_stream():
            return

        with self._lock:
            self._voices.append([samples, 0])

    def _ensure_stream(self):

        if self._stream is not None:
            return True

        try:

            self._stream = self._stream_factory(self._callback)
            self._stream.start()

        except Exception as e:

            log.info("Sound is unavailable: %s", e)

            self._failed = True
            self._stream = None

            return False

        return True

    def _callback(self, outdata, frames, time_info, status):

        out = np.zeros(frames, dtype="float32")

        with self._lock:

            alive = []

            for voice in self._voices:

                samples, position = voice

                chunk = samples[position:position + frames]

                out[: len(chunk)] += chunk

                voice[1] = position + len(chunk)

                if voice[1] < len(samples):
                    alive.append(voice)

            self._voices = alive

        out *= self.volume

        np.clip(out, -1.0, 1.0, out=out)

        outdata[:, 0] = out

    def set_enabled(self, enabled):

        self.enabled = bool(enabled)

        if not enabled:

            with self._lock:
                self._voices = []

    def close(self):

        if self._stream is not None:

            try:
                self._stream.stop()
                self._stream.close()

            finally:
                self._stream = None


def save_wav(path, samples):

    data = (np.clip(samples, -1, 1) * 32767).astype("<i2")

    with wave.open(str(path), "wb") as f:

        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(data.tobytes())


def main(argv):
    """
    Preview: play every sound (and save wavs if a folder is given).
    """

    sounds = render_all()

    if len(argv) > 1:

        from pathlib import Path

        folder = Path(argv[1])
        folder.mkdir(parents=True, exist_ok=True)

        for name, samples in sounds.items():
            save_wav(folder / f"{name}.wav", samples)

        print(f"Saved {len(sounds)} sounds to {folder}")

    mixer = SoundMixer(sounds=sounds)

    for name, samples in sounds.items():

        print(f"{name:8s} {len(samples) / SAMPLE_RATE:.2f}s")

        mixer.play(name)

        time.sleep(len(samples) / SAMPLE_RATE + 0.4)

    mixer.close()


if __name__ == "__main__":
    main(sys.argv)
