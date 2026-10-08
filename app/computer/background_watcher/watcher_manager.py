import threading


class WatcherManager:
    """
    Keeps the application index current while Sophia runs: every
    `interval` seconds it rescans for installed apps and rebuilds the
    index if anything changed, so a newly installed program can be
    opened without restarting Sophia.
    """

    def __init__(self, application_manager, interval=300):

        self.application_manager = application_manager
        self.interval = interval

        self._stop = threading.Event()
        self._thread = None

    def start(self):

        if self._thread is not None:
            return

        self._thread = threading.Thread(
            target=self._run,
            name="app-refresher",
            daemon=True,
        )

        self._thread.start()

    def stop(self):

        self._stop.set()

    def _run(self):

        # wait() returns True when stop() was called
        while not self._stop.wait(self.interval):

            try:
                self.application_manager.refresh_if_changed(quiet=True)

            except Exception:
                # A failed scan must never take Sophia down
                pass
