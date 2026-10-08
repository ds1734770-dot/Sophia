"""
Undo for reversible file changes (rename, move, copy, new folder, new
file) during this session.
"""

from collections import deque

MAX_UNDO = 20


class UndoStack:

    def __init__(self):

        self._items = deque(maxlen=MAX_UNDO)

    def push(self, description, action):
        """
        action() performs the reverse and returns (ok, message).
        """

        self._items.append((description, action))

    def peek(self):

        return self._items[-1][0] if self._items else None

    def describe(self):

        if not self._items:
            return "Nothing to undo."

        return "\n".join(
            f"{i}. {d}" for i, (d, _) in enumerate(reversed(self._items), start=1)
        )

    def undo(self):

        if not self._items:
            return False, "There is nothing to undo."

        description, action = self._items.pop()

        try:
            ok, message = action()

        except Exception as e:
            return False, f"I couldn't undo '{description}': {e}"

        if ok:
            return True, f"Undone: {description}. {message}".strip()

        return False, f"I couldn't undo '{description}': {message}"
