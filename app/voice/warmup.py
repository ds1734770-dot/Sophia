"""
Start-up order for the heavy voice parts. They all compete for the same
processor, and loading them at once made the wake word wait nearly 40
seconds. So the wake word goes first, and once it is listening the rest
load one after another: the speech model (needed for your first
request), the small model that double-checks the wake word, then the
spoken voice.
"""

import logging
import threading

log = logging.getLogger("sophia.voice")

# If the wake word never reports in (hands-free off, or it failed), load
# the rest after this many seconds anyway.
FALLBACK_SECONDS = 20


class WarmUp:
    """
    Runs the given loaders (callables) once, in order, in the background.
    Start it with go() (idempotent); arm() schedules go() as a fallback.
    """

    def __init__(self, loaders, fallback_seconds=FALLBACK_SECONDS):

        self.loaders = list(loaders)
        self.fallback_seconds = fallback_seconds

        self._started = threading.Event()
        self._lock = threading.Lock()
        self._timer = None
        self.done = threading.Event()

    def arm(self):
        """
        Make sure the loading starts even if go() is never called.
        """

        self._timer = threading.Timer(self.fallback_seconds, self.go)
        self._timer.daemon = True
        self._timer.start()

    def go(self):

        with self._lock:

            if self._started.is_set():
                return

            self._started.set()

        if self._timer is not None:
            self._timer.cancel()

        threading.Thread(target=self._run, name="warm-up", daemon=True).start()

    def _run(self):

        for loader in self.loaders:

            try:
                loader()

            except Exception:
                log.exception("Loading in the background failed")

        self.done.set()
