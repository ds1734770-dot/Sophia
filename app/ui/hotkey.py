"""
A global hotkey (Ctrl+Alt+Space) that works even when Sophia's window
is hidden. Uses the Win32 RegisterHotKey call.
"""

import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

log = logging.getLogger("sophia.ui")

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20

HOTKEY_ID = 0x50F1


MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

MODIFIERS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "shift": MOD_SHIFT, "win": MOD_WIN}


def parse_hotkey(text):
    """
    "alt+s" -> (MOD_ALT, ord("S"), "Alt+S"). Returns None if the text
    is not a modifier plus one letter, digit, space or F-key.
    """

    parts = [p.strip().lower() for p in text.split("+") if p.strip()]

    if len(parts) < 2:
        return None

    *mods, key = parts

    if any(m not in MODIFIERS for m in mods):
        return None

    modifiers = 0

    for m in mods:
        modifiers |= MODIFIERS[m]

    if key == "space":
        code = VK_SPACE

    elif len(key) == 1 and key.isalnum():
        code = ord(key.upper())

    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        code = 0x6F + int(key[1:])

    else:
        return None

    label = "+".join(m.title() for m in mods) + "+" + key.upper()

    return modifiers, code, label


class HotkeyFilter(QAbstractNativeEventFilter):

    def __init__(self, callback, candidates=None, hotkey_id=HOTKEY_ID):

        super().__init__()

        self.callback = callback
        self.registered = False
        self.hotkey_id = hotkey_id

        if candidates is not None:
            self.CANDIDATES = candidates

    # Tried in order; another program may already own one of them
    CANDIDATES = [
        (MOD_CONTROL | MOD_ALT, VK_SPACE, "Ctrl+Alt+Space"),
        (MOD_CONTROL | MOD_ALT, ord("S"), "Ctrl+Alt+S"),
        (MOD_CONTROL | MOD_ALT, ord("J"), "Ctrl+Alt+J"),
    ]

    def register(self):
        """
        Register the first free hotkey. Returns its label (for example
        "Ctrl+Alt+S"), or None if every candidate is taken.
        """

        self.label = None

        for modifiers, key, label in self.CANDIDATES:

            try:

                ok = ctypes.windll.user32.RegisterHotKey(
                    None, self.hotkey_id, modifiers | MOD_NOREPEAT, key
                )

            except Exception as e:

                log.warning("Hotkey unavailable: %s", e)

                return None

            if ok:

                self.registered = True
                self.label = label

                return label

        return None

    def unregister(self):

        if self.registered:

            ctypes.windll.user32.UnregisterHotKey(None, self.hotkey_id)
            self.registered = False

    def nativeEventFilter(self, event_type, message):

        if event_type == b"windows_generic_MSG":

            msg = wintypes.MSG.from_address(int(message))

            if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:

                self.callback()

                return True, 0

        return False, 0
