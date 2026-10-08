"""
Acting on the screen like a person: find something by looking at it,
then click, type or press keys.

The "eyes" are Gemini: it is shown a screenshot and asked where an
element is. The "hands" are pyautogui.
"""

import json
import logging
import time

log = logging.getLogger("sophia.screen")

# keys and combinations that must never be sent
BLOCKED_COMBOS = {
    ("ctrl", "alt", "delete"),
    ("ctrl", "shift", "esc"),
    ("win", "l"),
}

MAX_TYPED_CHARS = 2000
CLICK_PAUSE = 0.25


def parse_point(text):
    """
    Read Gemini's answer {"point": [y, x]} (each 0-1000). Returns
    (y, x) or None when the element was not found.
    """

    try:
        data = json.loads(text)

    except (TypeError, ValueError):
        return None

    point = data.get("point") if isinstance(data, dict) else None

    if not point or len(point) != 2:
        return None

    try:

        y, x = float(point[0]), float(point[1])

    except (TypeError, ValueError):
        return None

    if not (0 <= y <= 1000 and 0 <= x <= 1000):
        return None

    return y, x


class PyAutoGuiBackend:
    """
    The real mouse and keyboard.
    """

    def __init__(self):

        import pyautogui

        pyautogui.FAILSAFE = True      # mouse to a corner aborts
        pyautogui.PAUSE = 0.05

        self.gui = pyautogui

    def size(self):

        size = self.gui.size()

        return size.width, size.height

    def click(self, x, y, button="left", double=False):

        self.gui.moveTo(x, y, duration=0.2)

        time.sleep(CLICK_PAUSE)

        self.gui.click(x, y, button=button, clicks=2 if double else 1)

    def write(self, text):

        self.gui.write(text, interval=0.01)

    def hotkey(self, *keys):

        self.gui.hotkey(*keys)

    def press(self, key):

        self.gui.press(key)

    def scroll(self, amount):

        self.gui.scroll(amount)


class ScreenControl:

    def __init__(self, capture_png, locate, backend=None, clipboard=None):
        """
        capture_png(): screen as PNG bytes.
        locate(description, png): Gemini's JSON answer (text).
        clipboard: object with get()/set(), used to type non-ASCII text.
        """

        self.capture_png = capture_png
        self.locate = locate
        self._backend = backend
        self.clipboard = clipboard

    @property
    def backend(self):

        if self._backend is None:
            self._backend = PyAutoGuiBackend()

        return self._backend

    # ------------------------------------------------

    def click_on(self, description, button="left", double=False):
        """
        Find `description` on the screen and click it.
        Returns (ok, message).
        """

        png = self.capture_png()

        try:
            answer = self.locate(description, png)

        except Exception as e:

            log.warning("Locating failed: %s", e)

            return False, "I couldn't look at the screen right now."

        point = parse_point(answer)

        if point is None:
            return False, f"I couldn't see '{description}' on the screen."

        y, x = point

        width, height = self.backend.size()

        px = int(round(x / 1000 * width))
        py = int(round(y / 1000 * height))

        self.backend.click(px, py, button=button, double=double)

        return True, f"Clicked '{description}' at ({px}, {py})."

    def type_text(self, text, press_enter=False):

        if len(text) > MAX_TYPED_CHARS:
            return False, f"That is too long to type ({MAX_TYPED_CHARS} characters at most)."

        if text.isascii():

            self.backend.write(text)

        elif self.clipboard is not None:

            # keyboard emulation cannot type most non-English characters
            previous = self.clipboard.get()

            self.clipboard.set(text)
            self.backend.hotkey("ctrl", "v")

            time.sleep(0.2)

            if previous is not None:
                self.clipboard.set(previous)

        else:

            return False, "I can only type plain English letters here."

        if press_enter:
            self.backend.press("enter")

        return True, f"Typed {len(text)} characters."

    def press_keys(self, keys):
        """
        keys like "ctrl+c", "alt+tab", "enter", "win+d".
        """

        parts = tuple(k.strip().lower() for k in keys.replace(" ", "").split("+") if k.strip())

        if not parts or len(parts) > 4:
            return False, "Give 1 to 4 keys joined with +, like ctrl+c."

        if parts in BLOCKED_COMBOS:
            return False, "I won't send that key combination."

        if len(parts) == 1:
            self.backend.press(parts[0])

        else:
            self.backend.hotkey(*parts)

        return True, f"Pressed {'+'.join(parts)}."

    def scroll(self, direction, amount=5):

        amount = max(1, min(int(amount), 30))

        self.backend.scroll(amount * 120 if direction == "up" else -amount * 120)

        return True, f"Scrolled {direction}."
