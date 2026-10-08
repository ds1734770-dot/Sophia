"""
Process and window control for any running application.

Closing is graceful by default (taskkill without /F asks the app to
close, so it can offer to save work). Forcing is a separate, explicit
step.
"""

import csv
import io
import os
import subprocess
import time

try:
    import win32con
    import win32gui
except ImportError:  # not on Windows
    win32con = None
    win32gui = None


class WindowManager:

    ACTIONS = ("focus", "minimize", "maximize", "restore")

    def __init__(self):

        self.run = subprocess.run

    # ------------------------------------------------
    # Processes
    # ------------------------------------------------

    def running_processes(self):
        """
        Names of running programs, e.g. {"chrome.exe", "Code.exe"}.
        """

        result = self.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
        )

        names = set()

        for row in csv.reader(io.StringIO(result.stdout)):

            if row:
                names.add(row[0])

        return names

    def guess_process(self, app_name):
        """
        Find a running program that matches an app name, for apps with
        no known exe (Store apps, shortcuts). Returns its file name or
        None. Matches whole-ish names only so "code" does not hit
        "CodeSetup.exe".
        """

        wanted = "".join(ch for ch in app_name.lower() if ch.isalnum())

        if len(wanted) < 4:
            return None

        matches = []

        for name in self.running_processes():

            stem = "".join(
                ch for ch in os.path.splitext(name)[0].lower() if ch.isalnum()
            )

            if stem == wanted or stem.startswith(wanted):
                matches.append(name)

        return min(matches, key=len) if matches else None

    def is_running(self, process_name):

        return process_name.lower() in {
            n.lower() for n in self.running_processes()
        }

    def close(self, process_name, force=False, wait_seconds=3):
        """
        Ask a program to close. Returns (success, message).
        """

        if not self.is_running(process_name):
            return False, f"{process_name} isn't running."

        command = ["taskkill", "/IM", process_name]

        if force:
            command.append("/F")

        self.run(command, capture_output=True, text=True)

        deadline = time.time() + wait_seconds

        while time.time() < deadline:

            if not self.is_running(process_name):
                return True, f"Closed {process_name}."

            time.sleep(0.3)

        if self.is_running(process_name):

            return False, (
                f"{process_name} is still open; it may be asking to "
                "save work. Say 'force close' if you want to end it anyway."
            )

        return True, f"Closed {process_name}."

    # ------------------------------------------------
    # Windows
    # ------------------------------------------------

    def find_windows(self, text):
        """
        Visible top-level windows whose title contains `text`.
        """

        if win32gui is None:
            return []

        text = text.lower().strip()

        found = []

        def visit(hwnd, _):

            if not win32gui.IsWindowVisible(hwnd):
                return

            title = win32gui.GetWindowText(hwnd)

            if title and text in title.lower():
                found.append((hwnd, title))

        win32gui.EnumWindows(visit, None)

        return found

    def window_action(self, text, action):
        """
        focus / minimize / maximize / restore the first window whose
        title contains `text`. Returns (success, message).
        """

        if action not in self.ACTIONS:
            return False, f"Unknown window action '{action}'."

        windows = self.find_windows(text)

        if not windows:
            return False, f"I couldn't find an open window for '{text}'."

        hwnd, title = windows[0]

        show = {
            "focus": win32con.SW_RESTORE,
            "restore": win32con.SW_RESTORE,
            "minimize": win32con.SW_MINIMIZE,
            "maximize": win32con.SW_MAXIMIZE,
        }[action]

        win32gui.ShowWindow(hwnd, show)

        if action in ("focus", "restore", "maximize"):

            try:
                win32gui.SetForegroundWindow(hwnd)

            except Exception:
                # Windows sometimes refuses to steal focus
                pass

        verb = {
            "focus": "Switched to",
            "restore": "Restored",
            "minimize": "Minimized",
            "maximize": "Maximized",
        }[action]

        return True, f"{verb} '{title}'."


def process_name_for(application):
    """
    The program file name of a discovered application record, or None.
    """

    if application.get("process"):
        return application["process"]

    exe = application.get("exe")

    if exe:
        return os.path.basename(exe)

    return None
