"""
What Sophia knows about this computer before the user says anything, so
Gemini can answer "open my downloads" or "which apps do I have?" without
spending tool calls (and seconds) finding out: the user, the PC, the
everyday folders, the installed programs and what is open right now.
"""

import getpass
import platform
import sys
import time
from pathlib import Path

IS_MAC = sys.platform == "darwin"

try:
    import win32gui
except ImportError:      # not Windows
    win32gui = None

MAX_APPS = 70
MAX_WINDOWS = 12

_static = {"text": None, "built": 0.0}

STATIC_TTL = 600


def known_folders(home=None):

    home = Path(home or Path.home())

    found = []

    names = ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Movies") if IS_MAC else (
        "Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"
    )

    for name in names:

        # OneDrive may hold the real folder
        for base in (home / "OneDrive", home):

            path = base / name

            if path.is_dir():

                found.append(f"{name}: {path}")

                break

    return found


def installed_app_names(applications):

    names = sorted(
        {a.get("name", "") for a in applications if a.get("name")},
        key=lambda n: (len(n), n.lower()),
    )

    return names[:MAX_APPS]


def open_windows():
    """
    Titles of the visible windows (the programs the user has open).
    """

    if IS_MAC:

        try:

            from app.computer.macos import open_window_titles

            return open_window_titles(MAX_WINDOWS)

        except Exception:
            return []

    if win32gui is None:
        return []

    titles = []

    def visit(hwnd, _):

        if not win32gui.IsWindowVisible(hwnd):
            return

        title = win32gui.GetWindowText(hwnd).strip()

        if title and title not in ("Program Manager", "Sophia") and title not in titles:
            titles.append(title)

    try:
        win32gui.EnumWindows(visit, None)

    except Exception:
        return []

    return titles[:MAX_WINDOWS]


def build_static(applications, home=None):

    lines = [
        (
            f"Computer: {platform.node()}, macOS {platform.mac_ver()[0]}, "
            f"user '{getpass.getuser()}'."
        ) if IS_MAC else (
            f"Computer: {platform.node()}, {platform.system()} {platform.release()}, "
            f"Windows user '{getpass.getuser()}'."
        ),
        "Everyday folders: " + "; ".join(known_folders(home)) + ".",
    ]

    names = installed_app_names(applications)

    if names:
        lines.append(
            "Installed programs include: " + ", ".join(names)
            + ". (open_application can open any of them by name.)"
        )

    return "\n".join(lines)


def system_profile(load_applications, home=None, now=time.monotonic):
    """
    The computer description for the system prompt. The installed-program
    list is rebuilt every few minutes; open windows are read each time.
    """

    if _static["text"] is None or now() - _static["built"] > STATIC_TTL:

        try:
            _static["text"] = build_static(load_applications(), home)

        except Exception:
            _static["text"] = ""

        _static["built"] = now()

    text = _static["text"]

    titles = open_windows()

    if titles:
        text += "\nOpen right now: " + " | ".join(titles)

    return text
