"""
What the screen agent sees: the window the user is in and its numbered
controls, and after every action a short note of what changed, so the
model can tell whether its action worked.
"""

import time
from dataclasses import dataclass, field

MAX_LISTED = 70
NAME_LIMIT = 52


@dataclass
class Observation:
    title: str
    process: str
    elements: list = field(default_factory=list)
    taken: float = field(default_factory=time.monotonic)

    def keys(self):
        """
        What is on the screen, as a set (for finding what changed).
        """

        return {(e.kind, e.name.strip().lower()) for e in self.elements if e.name.strip()}


def describe(element):
    """
    '12 Button "Send"' (the number is what the model clicks).
    """

    name = " ".join((element.name or "").split())

    if len(name) > NAME_LIMIT:
        name = name[: NAME_LIMIT - 1] + "…"

    note = "" if element.enabled else " (disabled)"

    if element.password:
        note += " (password)"

    return f'{element.index} {element.kind} "{name}"{note}' if name else f"{element.index} {element.kind} (no name){note}"


class ScreenObserver:
    """
    Reads the screen through ScreenElements and remembers the last look,
    so numbers in the model's actions refer to what it was shown.
    """

    def __init__(self, elements):

        self.elements = elements
        self.last = None

    def observe(self, window_title=None):
        """
        Look at the window the user is working in (or one by title).
        """

        title, process, elements = self.elements.snapshot(window_title)

        observation = Observation(title or "", process or "", list(elements))

        self.previous, self.last = self.last, observation

        return observation

    previous = None

    def element(self, number):
        """
        The control with this number in the latest look, or None.
        """

        if self.last is None:
            return None

        for element in self.last.elements:

            if element.index == number:
                return element

        return None

    # ------------------------------------------------

    def render(self, observation, before=None, limit=MAX_LISTED):
        """
        The text the model reads.
        """

        lines = [
            f'Window: "{observation.title or "(none)"}"'
            + (f" ({observation.process})" if observation.process else "")
        ]

        if before is not None:

            lines.append(self._changes(before, observation))

        shown = observation.elements[:limit]

        if not shown:

            lines.append(
                "Controls: none readable here (a game, a picture or a custom-drawn window). "
                "Use screen_click_visual to click by description, or keyboard shortcuts."
            )

        else:

            lines.append("Controls (use these numbers):")
            lines.extend("  " + describe(e) for e in shown)

            more = len(observation.elements) - len(shown)

            if more > 0:
                lines.append(f"  ... {more} more not shown (scroll, or switch to what you need)")

        return "\n".join(lines)

    @staticmethod
    def _changes(before, after):

        notes = []

        if before.title != after.title:
            notes.append(f'the window changed from "{before.title}" to "{after.title}"')

        new = [name for kind, name in sorted(after.keys() - before.keys())]
        gone = before.keys() - after.keys()

        if new:
            notes.append("new on screen: " + ", ".join(f'"{n[:30]}"' for n in new[:6]) + (" ..." if len(new) > 6 else ""))

        if gone:
            notes.append(f"{len(gone)} controls went away")

        if not notes:
            return "Changes: nothing visibly changed."

        return "Changes: " + "; ".join(notes) + "."
