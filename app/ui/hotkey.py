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


class HotkeyFilter(QAbstractNativeEventFilter):

    def __init__(self, callback):

        super().__init__()

        self.callback = callback
        self.registered = False

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
                    None, HOTKEY_ID, modifiers | MOD_NOREPEAT, key
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

            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            self.registered = False

    def nativeEventFilter(self, event_type, message):

        if event_type == b"windows_generic_MSG":

            msg = wintypes.MSG.from_address(int(message))

            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:

                self.callback()

                return True, 0

        return False, 0
