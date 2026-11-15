"""
Screen controls on macOS through the Accessibility API (AXUIElement):
the Mac counterpart of UiaBackend in ui_automation.py, with the same
methods, so ScreenElements, the screen agent and the WhatsApp skill work
unchanged.

macOS only lets a program read other apps' controls after the user
allows it: System Settings > Privacy & Security > Accessibility, for the
app that starts Sophia (Terminal, iTerm, VS Code...).
"""

import logging
import os
import time
from dataclasses import dataclass

from app.computer.ui_automation import Element

log = logging.getLogger("sophia.uia")

MAX_NODES = 2500
TIME_BUDGET = 3.0
MAX_ELEMENTS = 220
MAX_DEPTH = 45

# AX role (or role/subrole) -> the control kinds the rest of Sophia uses
ROLE_KINDS = {
    "AXButton": "Button",
    "AXMenuButton": "Button",
    "AXDisclosureTriangle": "Button",
    "AXPopUpButton": "ComboBox",
    "AXComboBox": "ComboBox",
    "AXTextField": "Edit",
    "AXTextArea": "Edit",
    "AXSearchField": "Edit",
    "AXMenuItem": "MenuItem",
    "AXLink": "Hyperlink",
    "AXCheckBox": "CheckBox",
    "AXRadioButton": "RadioButton",
    "AXRow": "ListItem",
    "AXCell": "ListItem",
    "AXSlider": "Slider",
    "AXIncrementor": "Spinner",
    "AXWebArea": "Document",
}

SUBROLE_KINDS = {
    "AXTabButton": "TabItem",
    "AXSwitch": "CheckBox",
    "AXSearchField": "Edit",
    "AXOutlineRow": "TreeItem",
}

# attributes read in one call per control
ATTRIBUTES = [
    "AXRole", "AXSubrole", "AXTitle", "AXDescription", "AXValue", "AXHelp",
    "AXPlaceholderValue", "AXPosition", "AXSize", "AXEnabled", "AXChildren",
]

ROLE, SUBROLE, TITLE, DESCRIPTION, VALUE, HELP, PLACEHOLDER, POSITION, SIZE, ENABLED, CHILDREN = range(11)

NO_PERMISSION = (
    "macOS has not allowed Sophia to read other apps' buttons yet. Open System Settings > "
    "Privacy & Security > Accessibility, switch on the app you started Sophia from "
    "(Terminal, iTerm or VS Code), then restart Sophia."
)


class AccessibilityDenied(RuntimeError):
    pass


@dataclass
class MacWindow:
    """
    One app's front window.
    """

    app_name: str
    pid: int
    app: object
    window: object
    title: str


def _text(value):

    if value is None:
        return ""

    try:
        text = str(value)

    except Exception:
        return ""

    # AX error placeholders and object descriptions are not names
    if text.startswith("<") and text.endswith(">"):
        return ""

    return " ".join(text.split())


class MacAxBackend:

    def __init__(self, ax=None, workspace=None, frontmost=None):

        if ax is None:
            import ApplicationServices as ax

        self.ax = ax
        self._workspace = workspace
        self._frontmost = frontmost
        self._prompted = False

    # ---- low level ----

    def _require_trust(self):

        ax = self.ax

        if ax.AXIsProcessTrusted():
            return

        if not self._prompted:

            self._prompted = True

            try:
                # shows macOS's own "allow accessibility" prompt once
                ax.AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True})

            except Exception:
                pass

        raise AccessibilityDenied(NO_PERMISSION)

    def _get(self, element, attribute):

        try:
            err, value = self.ax.AXUIElementCopyAttributeValue(element, attribute, None)

        except Exception:
            return None

        return value if err == 0 else None

    def _many(self, element):
        """
        All of ATTRIBUTES at once, None where an attribute is missing.
        """

        ax = self.ax

        try:

            err, values = ax.AXUIElementCopyMultipleAttributeValues(element, ATTRIBUTES, 0, None)

            if err == 0 and values is not None and len(values) == len(ATTRIBUTES):
                return [self._clean_value(v) for v in values]

        except Exception:
            pass

        return [self._get(element, a) for a in ATTRIBUTES]

    def _clean_value(self, value):

        # missing attributes come back as AXValue objects of the error type
        try:

            if value is not None and self.ax.AXValueGetType(value) == self.ax.kAXValueAXErrorType:
                return None

        except Exception:
            pass

        return value

    def _point(self, value, kind):

        if value is None:
            return None

        try:

            ok, data = self.ax.AXValueGetValue(value, kind, None)

            return data if ok else None

        except Exception:
            return None

    def _frame(self, position, size):

        point = self._point(position, self.ax.kAXValueCGPointType)
        extent = self._point(size, self.ax.kAXValueCGSizeType)

        if point is None or extent is None:
            return None

        return int(point.x), int(point.y), int(extent.width), int(extent.height)

    def _running_apps(self):

        if self._workspace is not None:
            return self._workspace()

        from AppKit import NSWorkspace

        return list(NSWorkspace.sharedWorkspace().runningApplications())

    # ---- the backend interface ----

    def window(self, title=None):

        from app.computer.macos import clean_name

        self._require_trust()

        apps = []

        if title:

            wanted = title.strip().lower()

            for app in self._running_apps():

                if app.activationPolicy() != 0:
                    continue

                name = clean_name(app.localizedName() or "")

                if wanted in name.lower() or (name and name.lower() in wanted):
                    apps.append(app)

            apps.sort(key=lambda a: len(a.localizedName() or ""))

        else:

            if self._frontmost is not None:
                front = self._frontmost()

            else:

                from AppKit import NSWorkspace

                front = NSWorkspace.sharedWorkspace().frontmostApplication()

            if front is not None:
                apps.append(front)

        for app in apps:

            pid = int(app.processIdentifier())
            name = clean_name(app.localizedName() or "")
            element = self.ax.AXUIElementCreateApplication(pid)

            try:
                self.ax.AXUIElementSetMessagingTimeout(element, 1.0)

            except Exception:
                pass

            window = self._get(element, "AXFocusedWindow") or self._get(element, "AXMainWindow")

            if window is None:

                windows = self._get(element, "AXWindows") or []

                window = windows[0] if len(windows) else None

            if window is None:
                continue

            window_title = _text(self._get(window, "AXTitle"))

            # Sophia's own windows keep their name, so they are left alone
            if pid == os.getpid():
                label = "Sophia"

            elif not window_title:
                label = name

            elif name.lower() in window_title.lower():
                label = window_title

            else:
                label = f"{window_title} - {name}"

            return MacWindow(name, pid, element, window, label)

        return None

    def title(self, window):

        return window.title

    def process_name(self, window):

        return window.app_name

    def walk(self, window):
        """
        The interactive, visible controls of a window, in reading order.
        """

        elements = []
        seen = 0
        lookups = 0
        deadline = time.monotonic() + TIME_BUDGET

        def label_from_children(children):
            """
            Chat rows and cards often have no name of their own: read it
            from the text inside.
            """

            texts = []

            def collect(items, depth):

                for child in list(items or [])[:8]:

                    if len(texts) >= 4 or depth > 3:
                        return

                    values = self._many(child)

                    text = _text(values[VALUE]) or _text(values[TITLE]) or _text(values[DESCRIPTION])

                    if values[ROLE] == "AXStaticText" and text:
                        texts.append(text)

                    elif values[CHILDREN]:
                        collect(values[CHILDREN], depth + 1)

            collect(children, 0)

            return " | ".join(texts)

        def visit(element, depth, parent_role=""):

            nonlocal seen, lookups

            if depth > MAX_DEPTH or seen > MAX_NODES or len(elements) >= MAX_ELEMENTS:
                return

            if time.monotonic() > deadline:
                return

            seen += 1

            values = self._many(element)

            role = _text(values[ROLE])
            subrole = _text(values[SUBROLE])
            kind = SUBROLE_KINDS.get(subrole) or ROLE_KINDS.get(role)

            # a table row's cells repeat the row
            if role == "AXCell" and parent_role in ("AXRow", "AXCell"):
                kind = None

            if kind and kind != "Document":

                frame = self._frame(values[POSITION], values[SIZE])

                if frame and frame[2] > 1 and frame[3] > 1:

                    x, y, width, height = frame

                    if kind == "Edit":
                        name = (
                            _text(values[TITLE]) or _text(values[DESCRIPTION])
                            or _text(values[PLACEHOLDER]) or _text(values[HELP])
                        )

                    else:
                        name = (
                            _text(values[TITLE]) or _text(values[DESCRIPTION])
                            or (_text(values[VALUE]) if kind not in ("CheckBox", "RadioButton", "Slider") else "")
                            or _text(values[HELP])
                        )

                    if not name and kind in ("ListItem", "TreeItem", "Button", "Hyperlink") and lookups < 60:

                        lookups += 1
                        name = label_from_children(values[CHILDREN])

                    enabled = values[ENABLED]

                    elements.append(Element(
                        index=len(elements) + 1,
                        kind=kind,
                        name=name,
                        x=x + width // 2,
                        y=y + height // 2,
                        width=width,
                        height=height,
                        enabled=True if enabled is None else bool(enabled),
                        password=subrole == "AXSecureTextField",
                        handle=element,
                    ))

            # a row's cells repeat the row; a button's insides are its label
            if kind in ("Button", "MenuItem", "CheckBox", "RadioButton", "Edit", "ComboBox"):
                return

            for child in list(values[CHILDREN] or []):
                visit(child, depth + 1, role)

        visit(window.window, 0)

        for i, element in enumerate(elements, start=1):
            element.index = i

        return elements

    # ---- acting on one control ----

    def press(self, element):

        try:
            return self.ax.AXUIElementPerformAction(element.handle, "AXPress") == 0

        except Exception:
            return False

    def set_value(self, element, text):

        try:
            return self.ax.AXUIElementSetAttributeValue(element.handle, "AXValue", text) == 0

        except Exception:
            return False

    def focus(self, element):

        try:
            self.ax.AXUIElementSetAttributeValue(element.handle, "AXFocused", True)

        except Exception:
            pass

    def focused(self):

        try:

            system = self.ax.AXUIElementCreateSystemWide()
            control = self._get(system, "AXFocusedUIElement")

            if control is None:
                return None

            values = self._many(control)

            name = _text(values[TITLE]) or _text(values[DESCRIPTION]) or _text(values[PLACEHOLDER])

            return name, _text(values[SUBROLE]) == "AXSecureTextField"

        except Exception:
            return None

    def read_text(self, window, limit=3000):

        parts = []
        size = 0
        deadline = time.monotonic() + 2.5

        def visit(element, depth):

            nonlocal size

            if depth > MAX_DEPTH or size >= limit or time.monotonic() > deadline:
                return

            values = self._many(element)

            if values[ROLE] == "AXStaticText":

                text = _text(values[VALUE]) or _text(values[TITLE])

                if text and (not parts or parts[-1] != text):

                    parts.append(text)
                    size += len(text) + 1

            for child in list(values[CHILDREN] or []):
                visit(child, depth + 1)

        visit(window.window, 0)

        return "\n".join(parts)[:limit]
