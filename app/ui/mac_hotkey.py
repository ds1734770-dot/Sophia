"""
Global hotkeys on macOS through Carbon's RegisterEventHotKey: they work
while another app is in front, and need no Accessibility or Input
Monitoring permission. Same interface as the Windows HotkeyFilter.

On a Mac "alt" is the Option key and "win" is Command, so the Windows
defaults keep working: Ctrl+Option+Space, Option+S, Ctrl+Option+X.
"""

import ctypes
import ctypes.util
import logging
import struct

from PySide6.QtCore import QAbstractNativeEventFilter

log = logging.getLogger("sophia.ui")

# Carbon modifier masks
CMD_KEY = 0x0100
SHIFT_KEY = 0x0200
OPTION_KEY = 0x0800
CONTROL_KEY = 0x1000

MODIFIERS = {
    "alt": OPTION_KEY, "option": OPTION_KEY, "opt": OPTION_KEY,
    "ctrl": CONTROL_KEY, "control": CONTROL_KEY,
    "shift": SHIFT_KEY,
    "win": CMD_KEY, "cmd": CMD_KEY, "command": CMD_KEY,
}

MODIFIER_LABELS = {
    "alt": "Option", "option": "Option", "opt": "Option",
    "ctrl": "Ctrl", "control": "Ctrl", "shift": "Shift",
    "win": "Cmd", "cmd": "Cmd", "command": "Cmd",
}

# Mac virtual key codes (ANSI layout)
KEY_CODES = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05,
    "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C,
    "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10, "t": 0x11, "1": 0x12,
    "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "9": 0x19,
    "7": 0x1A, "8": 0x1C, "0": 0x1D, "o": 0x1F, "u": 0x20, "i": 0x22,
    "p": 0x23, "l": 0x25, "j": 0x26, "k": 0x28, "n": 0x2D, "m": 0x2E,
    "space": 0x31,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60, "f6": 0x61,
    "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
}


def fourcc(text):

    return struct.unpack(">I", text.encode("ascii"))[0]


K_EVENT_CLASS_KEYBOARD = fourcc("keyb")
K_EVENT_HOTKEY_PRESSED = 5
K_EVENT_PARAM_DIRECT_OBJECT = fourcc("----")
TYPE_EVENT_HOTKEY_ID = fourcc("hkid")
SIGNATURE = fourcc("SOPH")


def parse_hotkey(text):
    """
    "alt+s" -> (OPTION_KEY, key code of S, "Option+S"), or None.
    """

    parts = [p.strip().lower() for p in text.split("+") if p.strip()]

    if len(parts) < 2:
        return None

    *mods, key = parts

    if any(m not in MODIFIERS for m in mods) or key not in KEY_CODES:
        return None

    modifiers = 0

    for m in mods:
        modifiers |= MODIFIERS[m]

    label = "+".join(MODIFIER_LABELS[m] for m in mods) + "+" + key.upper()

    return modifiers, KEY_CODES[key], label


class EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


HANDLER = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)


class _Carbon:
    """
    One event handler for all of Sophia's hotkeys; it calls the callback
    registered for the pressed hotkey's id.
    """

    def __init__(self):

        path = ctypes.util.find_library("Carbon")

        if not path:
            raise OSError("Carbon framework not found")

        lib = ctypes.CDLL(path)

        lib.GetApplicationEventTarget.restype = ctypes.c_void_p

        lib.InstallEventHandler.argtypes = [
            ctypes.c_void_p, HANDLER, ctypes.c_uint32,
            ctypes.POINTER(EventTypeSpec), ctypes.c_void_p, ctypes.c_void_p,
        ]
        lib.InstallEventHandler.restype = ctypes.c_int32

        lib.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, EventHotKeyID,
            ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
        ]
        lib.RegisterEventHotKey.restype = ctypes.c_int32

        lib.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        lib.UnregisterEventHotKey.restype = ctypes.c_int32

        lib.GetEventParameter.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p,
        ]
        lib.GetEventParameter.restype = ctypes.c_int32

        self.lib = lib
        self.callbacks = {}

        # kept alive for as long as the handler is installed
        self._handler = HANDLER(self._on_event)

        spec = EventTypeSpec(K_EVENT_CLASS_KEYBOARD, K_EVENT_HOTKEY_PRESSED)

        status = lib.InstallEventHandler(
            lib.GetApplicationEventTarget(), self._handler, 1,
            ctypes.byref(spec), None, None,
        )

        if status != 0:
            raise OSError(f"InstallEventHandler failed ({status})")

    def _on_event(self, _call_ref, event, _user_data):

        hotkey = EventHotKeyID()

        self.lib.GetEventParameter(
            event, K_EVENT_PARAM_DIRECT_OBJECT, TYPE_EVENT_HOTKEY_ID, None,
            ctypes.sizeof(hotkey), None, ctypes.byref(hotkey),
        )

        callback = self.callbacks.get(hotkey.id)

        if callback is not None:

            try:
                callback()

            except Exception:
                log.exception("Hotkey action failed")

        return 0

    def register(self, hotkey_id, modifiers, key, callback):

        ref = ctypes.c_void_p()

        status = self.lib.RegisterEventHotKey(
            key, modifiers, EventHotKeyID(SIGNATURE, hotkey_id),
            self.lib.GetApplicationEventTarget(), 0, ctypes.byref(ref),
        )

        if status != 0:
            return None

        self.callbacks[hotkey_id] = callback

        return ref

    def unregister(self, hotkey_id, ref):

        self.callbacks.pop(hotkey_id, None)

        if ref:
            self.lib.UnregisterEventHotKey(ref)


_carbon = None


def carbon():

    global _carbon

    if _carbon is None:
        _carbon = _Carbon()

    return _carbon


class MacHotkeyFilter(QAbstractNativeEventFilter):

    # Tried in order; another app may already own one of them
    CANDIDATES = [
        (CONTROL_KEY | OPTION_KEY, KEY_CODES["space"], "Ctrl+Option+Space"),
        (CONTROL_KEY | OPTION_KEY, KEY_CODES["s"], "Ctrl+Option+S"),
        (CONTROL_KEY | OPTION_KEY, KEY_CODES["j"], "Ctrl+Option+J"),
    ]

    def __init__(self, callback, candidates=None, hotkey_id=0x50F1):

        super().__init__()

        self.callback = callback
        self.registered = False
        self.hotkey_id = hotkey_id
        self.label = None
        self._ref = None

        if candidates is not None:
            self.CANDIDATES = candidates

    def register(self):

        self.label = None

        try:
            lib = carbon()

        except Exception as e:

            log.warning("Hotkey unavailable: %s", e)

            return None

        for modifiers, key, label in self.CANDIDATES:

            ref = lib.register(self.hotkey_id, modifiers, key, self.callback)

            if ref is not None:

                self._ref = ref
                self.registered = True
                self.label = label

                return label

        return None

    def unregister(self):

        if self.registered:

            carbon().unregister(self.hotkey_id, self._ref)

            self._ref = None
            self.registered = False

    def nativeEventFilter(self, event_type, message):

        # Carbon calls the handler directly; nothing to filter
        return False, 0
