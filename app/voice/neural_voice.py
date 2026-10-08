"""
A natural-sounding voice using Microsoft Edge's neural voices (the
edge-tts package; free, needs an internet connection). If it cannot be
reached, speech falls back to the offline Windows voice.
"""

import asyncio
import io
import logging

log = logging.getLogger("sophia.voice")

DEFAULT_VOICE = "en-IN-NeerjaNeural"


def synthesize_mp3(text, voice):
    """
    Text -> MP3 bytes using edge-tts.
    """

    import edge_tts

    async def run():

        chunks = []

        async for chunk in edge_tts.Communicate(text, voice).stream():

            if chunk["type"] == "audio":
                chunks.append(chunk["data"])

        return b"".join(chunks)

    return asyncio.run(run())


def decode_mp3(data):
    """
    MP3 bytes -> (float32 mono samples, sample rate), using PyAV
    (installed with faster-whisper).
    """

    import av
    import numpy as np

    container = av.open(io.BytesIO(data))

    stream = container.streams.audio[0]

    resampler = av.AudioResampler(format="flt", layout="mono", rate=24000)

    frames = []

    for frame in container.decode(stream):

        for out in resampler.resample(frame):
            frames.append(out.to_ndarray().reshape(-1))

    container.close()

    if not frames:
        return np.zeros(0, dtype="float32"), 24000

    return np.concatenate(frames).astype("float32"), 24000


class SoundOutput:
    """
    Plays audio with sounddevice.
    """

    def __init__(self):

        import sounddevice

        self.sd = sounddevice

    def play(self, samples, rate):

        self.sd.play(samples, rate)

    def busy(self):

        stream = self.sd.get_stream()

        return bool(stream is not None and stream.active)

    def stop(self):

        self.sd.stop()


class EdgeBackend:
    """
    Speaker backend (see app.voice.speaker.Speaker): start / done /
    purge. If synthesis fails, the fallback backend speaks instead.
    """

    def __init__(
        self,
        voice=DEFAULT_VOICE,
        fallback=None,
        synthesize=synthesize_mp3,
        decode=decode_mp3,
        output=None,
    ):

        self.voice = voice
        self.fallback = fallback

        self._synthesize = synthesize
        self._decode = decode
        self._output = output

        self._using_fallback = False

    @property
    def output(self):

        if self._output is None:
            self._output = SoundOutput()

        return self._output

    def start(self, text):

        self._using_fallback = False

        try:

            samples, rate = self._decode(self._synthesize(text, self.voice))

            if len(samples) == 0:
                raise RuntimeError("no audio")

            self.output.play(samples, rate)

        except Exception as e:

            log.info("Neural voice unavailable (%s); using the Windows voice", e)

            if self.fallback is None:
                raise

            self._using_fallback = True

            self.fallback.start(text)

    def done(self, timeout_ms):

        if self._using_fallback:
            return self.fallback.done(timeout_ms)

        import time

        deadline = time.time() + timeout_ms / 1000

        while time.time() < deadline:

            if not self.output.busy():
                return True

            time.sleep(0.02)

        return not self.output.busy()

    def purge(self):

        if self._using_fallback:

            self.fallback.purge()

            return

        self.output.stop()
