"""
Text-to-speech through the Windows speech engine (SAPI): offline, free,
no AI quota.
"""

import logging
import queue
import re
import threading

log = logging.getLogger("sophia.voice")

MAX_SPOKEN_CHARS = 1200


def speakable(text):
    """
    Turn a chat reply into something pleasant to hear: no markdown
    symbols, no raw links, no code blocks, bounded length.
    """

    text = re.sub(r"```.*?```", " (code omitted) ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", " a link ", text)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_~>|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > MAX_SPOKEN_CHARS:

        cut = text[:MAX_SPOKEN_CHARS]

        # end on a sentence boundary when there is one
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))

        text = (cut[: end + 1] if end > 200 else cut) + " ..."

    return text


class SapiBackend:
    """
    Talks to SAPI. COM objects belong to the thread that created them,
    so this is only ever used from the Speaker's worker thread.
    """

    def __init__(self, rate=0):

        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()

        self.voice = win32com.client.Dispatch("SAPI.SpVoice")
        self.voice.Rate = rate

    ASYNC = 1
    PURGE = 2

    def start(self, text):

        self.voice.Speak(text, self.ASYNC)

    def done(self, timeout_ms):

        return bool(self.voice.WaitUntilDone(timeout_ms))

    def purge(self):

        self.voice.Speak("", self.ASYNC | self.PURGE)


class Speaker:

    _STOP = object()
    _QUIT = object()

    def __init__(self, backend_factory=None, enabled=True):

        self.enabled = enabled

        self._backend_factory = backend_factory or SapiBackend
        self._queue = queue.Queue()
        self._interrupt = threading.Event()
        self._thread = None
        self.speaking = threading.Event()

    # ------------------------------------------------

    def _ensure_thread(self):

        if self._thread is None:

            self._thread = threading.Thread(
                target=self._run, name="speaker", daemon=True
            )

            self._thread.start()

    def say(self, text, interrupt=True):
        """
        Speak a reply (non-blocking).
        """

        if not self.enabled:
            return

        text = speakable(text)

        if not text:
            return

        self._ensure_thread()

        if interrupt:
            self.stop()

        self._queue.put(text)

    def stop(self):
        """
        Cut off speech that is in progress and drop anything queued.
        """

        self._interrupt.set()

        try:
            while True:
                self._queue.get_nowait()

        except queue.Empty:
            pass

    def close(self):

        if self._thread is not None:

            self._queue.put(self._QUIT)
            self._thread.join(timeout=2)
            self._thread = None

    # ------------------------------------------------

    def _run(self):

        try:
            backend = self._backend_factory()

        except Exception as e:

            log.warning("Speech engine unavailable: %s", e)
            self.enabled = False

            return

        while True:

            item = self._queue.get()

            if item is self._QUIT:
                return

            self._interrupt.clear()
            self.speaking.set()

            try:

                backend.start(item)

                while not backend.done(100):

                    if self._interrupt.is_set():

                        backend.purge()
                        break

            except Exception as e:

                log.warning("Speech failed: %s", e)

            finally:

                self.speaking.clear()
