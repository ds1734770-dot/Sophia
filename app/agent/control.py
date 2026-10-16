"""
Holds a screen task on a leash: a limit on steps and time, and an
emergency stop that works from anywhere (hotkey, the Stop button, the
mouse in a screen corner).
"""

import threading
import time

DEFAULT_MAX_STEPS = 25
DEFAULT_MAX_SECONDS = 180


class AgentControl:

    def __init__(
        self,
        max_steps=DEFAULT_MAX_STEPS,
        max_seconds=DEFAULT_MAX_SECONDS,
        clock=time.monotonic,
    ):

        self.max_steps = max_steps
        self.max_seconds = max_seconds
        self._clock = clock

        self.stop_event = threading.Event()
        self.reason = ""

        self.active = False
        self.goal = ""
        self.steps = 0

        self._started = 0.0

        # called with True when a task starts and False when it ends
        self.listeners = []

    def begin(self, goal):

        self.stop_event.clear()
        self.reason = ""
        self.goal = goal
        self.steps = 0
        self._started = self._clock()
        self.active = True

        self._notify(True)

    def end(self):

        self.active = False

        self._notify(False)

    def stop(self, reason="You stopped me."):
        """
        The emergency stop: the next action is refused and the task ends.
        """

        self.reason = reason

        self.stop_event.set()

    def check(self):
        """
        None if the task may go on, otherwise why it must end.
        """

        if self.stop_event.is_set():
            return self.reason or "You stopped me."

        # no task running: nothing to limit
        if not self.active:
            return None

        if self.steps >= self.max_steps:
            return f"I reached my limit of {self.max_steps} steps for one task."

        if self._clock() - self._started > self.max_seconds:
            return f"I reached my time limit of {self.max_seconds} seconds for one task."

        return None

    def count_step(self):

        self.steps += 1

    def _notify(self, active):

        for listener in list(self.listeners):

            try:
                listener(active)

            except Exception:
                pass
