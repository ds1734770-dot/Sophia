"""
macOS versions of the things Sophia does through Windows APIs elsewhere:
finding and opening apps, closing them, moving windows, folders, volume,
brightness, power, the clipboard, Spotlight search and start at login.

Everything here uses tools that ship with macOS (open, osascript, pmset,
mdfind, pbcopy) or PyObjC, so nothing extra has to be installed. Calls
that drive other apps through System Events need Accessibility
permission for the program that runs Sophia (Terminal, VS Code...).
"""

import logging
import os
import plistlib
import posixpath
import subprocess
import sys
import threading
from pathlib import Path

log = logging.getLogger("sophia.mac")

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"


# ---------------------------------------------------------------
# Basics
# ---------------------------------------------------------------

def osascript(script, timeout=10, run=subprocess.run):
    """
    Run AppleScript. Returns (ok, output or error text).
    """

    try:

        result = run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    except subprocess.TimeoutExpired:
        return False, "AppleScript took too long."

    except OSError as e:
        return False, str(e)

    if result.returncode != 0:
        return False, (result.stderr or "").strip()

    return True, (result.stdout or "").strip()


def applescript_string(text):
    """
    A Python string as an AppleScript string literal.
    """

    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def open_path(target):
    """
    Open a file, folder, app bundle or URL the way a double-click would
    (the macOS counterpart of os.startfile).
    """

    if IS_WINDOWS:
        os.startfile(target)  # noqa: S606 (Windows only)
        return

    subprocess.Popen(
        ["open", str(target)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------
# Applications
# ---------------------------------------------------------------

# some apps (WhatsApp) put invisible direction marks in their names
INVISIBLE = dict.fromkeys(map(ord, "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff"))


def clean_name(name):

    return str(name).translate(INVISIBLE).strip()

APP_FOLDERS = [
    Path("/Applications"),
    Path("/Applications/Utilities"),
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path.home() / "Applications",
    Path.home() / "Applications" / "Chrome Apps.localized",
    Path("/System/Library/CoreServices/Applications"),
]

EXTRA_APPS = [
    Path("/System/Library/CoreServices/Finder.app"),
]


def bundle_info(app_path):
    """
    (display name, executable name) from an app's Info.plist.
    """

    name = Path(app_path).stem
    executable = name

    try:

        with open(Path(app_path) / "Contents" / "Info.plist", "rb") as f:
            info = plistlib.load(f)

        name = info.get("CFBundleDisplayName") or info.get("CFBundleName") or name
        executable = info.get("CFBundleExecutable") or executable

    except Exception:
        pass

    return clean_name(name), str(executable)


def installed_apps(folders=None):
    """
    Every .app in the usual places, one level deep (plus folders like
    /Applications/Microsoft Office/ that group several apps).
    """

    found = []
    seen = set()

    def add(app):

        key = app.name.lower()

        if key in seen:
            return

        seen.add(key)
        found.append(app)

    for folder in folders or APP_FOLDERS:

        try:
            entries = sorted(folder.iterdir())

        except OSError:
            continue

        for entry in entries:

            if entry.suffix == ".app":
                add(entry)

            elif entry.is_dir() and not entry.name.startswith("."):

                try:
                    for inner in sorted(entry.glob("*.app")):
                        add(inner)

                except OSError:
                    pass

    if folders is None:
        for app in EXTRA_APPS:
            if app.exists():
                add(app)

    return found


def running_app_names():
    """
    Names of the apps the user has open (Dock apps), e.g. {"Safari"}.
    """

    try:

        from AppKit import NSWorkspace

        names = set()

        for app in NSWorkspace.sharedWorkspace().runningApplications():

            # 0 = regular app with a Dock icon
            if app.activationPolicy() == 0 and app.localizedName():
                names.add(clean_name(app.localizedName()))

        return names

    except Exception:

        ok, out = osascript(
            'tell application "System Events" to get name of '
            "(processes where background only is false)"
        )

        return {clean_name(n) for n in out.split(",") if clean_name(n)} if ok else set()


def running_process_names():
    """
    Names of all running processes (apps and command line tools).
    """

    import psutil

    names = set(running_app_names())

    for p in psutil.process_iter(["name"]):

        if p.info.get("name"):
            names.add(p.info["name"])

    return names


def quit_app(name, force=False):
    """
    Ask an app to quit, like Cmd+Q (it may offer to save work), or end
    it at once. Returns True if a matching app or process was found.
    """

    wanted = clean_name(name).lower()

    try:

        from AppKit import NSWorkspace

        found = False

        for app in NSWorkspace.sharedWorkspace().runningApplications():

            if clean_name(app.localizedName() or "").lower() == wanted:

                found = True

                if force:
                    app.forceTerminate()

                else:
                    app.terminate()

        if found:
            return True

    except Exception:
        log.debug("NSWorkspace quit failed", exc_info=True)

    # command line programs have no app object
    if force:

        result = subprocess.run(["pkill", "-x", name], capture_output=True, text=True)

        return result.returncode == 0

    ok, _ = osascript(f"tell application {applescript_string(name)} to quit", timeout=15)

    if ok:
        return True

    result = subprocess.run(["pkill", "-TERM", "-x", name], capture_output=True, text=True)

    return result.returncode == 0


def window_action(text, action):
    """
    focus / minimize / maximize / restore the first app or window whose
    name contains `text`. Returns (success, message).
    """

    wanted = text.strip().lower()

    match = None

    for name in sorted(running_app_names(), key=len):

        if wanted in name.lower() or name.lower() in wanted:
            match = name
            break

    if match is None:
        return False, f"I couldn't find an open window for '{text}'."

    app = applescript_string(match)

    if action in ("focus", "restore"):

        script = f"tell application {app} to activate"

        if action == "restore":
            script = (
                f'tell application "System Events" to tell process {app}\n'
                '  repeat with w in windows\n'
                '    try\n'
                '      set value of attribute "AXMinimized" of w to false\n'
                '    end try\n'
                '  end repeat\n'
                'end tell\n'
                f"tell application {app} to activate"
            )

    elif action == "minimize":

        script = (
            f'tell application "System Events" to tell process {app}\n'
            '  set value of attribute "AXMinimized" of front window to true\n'
            'end tell'
        )

    elif action == "maximize":

        # zoom the front window to fill the screen it is on
        script = (
            f"tell application {app} to activate\n"
            'tell application "System Events" to tell process ' + app + "\n"
            '  try\n'
            '    click (first button of front window whose subrole is "AXZoomButton")\n'
            '  end try\n'
            'end tell'
        )

    else:
        return False, f"Unknown window action '{action}'."

    ok, error = osascript(script)

    if not ok:

        if "assistive" in error.lower() or "not allowed" in error.lower():

            return False, (
                "macOS blocked that. Allow the app that runs Sophia in "
                "System Settings > Privacy & Security > Accessibility."
            )

        return False, f"I couldn't {action} {match}: {error}"

    verb = {
        "focus": "Switched to",
        "restore": "Restored",
        "minimize": "Minimized",
        "maximize": "Maximized",
    }[action]

    return True, f"{verb} '{match}'."


def open_window_titles(limit=15):
    """
    "App: window title" for the windows on screen, front first. Titles
    need Screen Recording permission; without it only app names show.
    """

    try:

        import Quartz

        options = (
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements
        )

        windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []

    except Exception:
        return sorted(running_app_names())[:limit]

    titles = []

    for w in windows:

        # layer 0 = normal app windows (not the menu bar or Dock)
        if w.get("kCGWindowLayer", 0) != 0:
            continue

        owner = clean_name(w.get("kCGWindowOwnerName") or "")
        title = str(w.get("kCGWindowName") or "").strip()

        if not owner or owner in ("Sophia", "Window Server", "Dock"):
            continue

        if "python" in owner.lower() and title in ("", "Sophia"):
            continue

        label = f"{owner}: {title}" if title else owner

        if label not in titles:
            titles.append(label)

        if len(titles) >= limit:
            break

    return titles


# ---------------------------------------------------------------
# Folders
# ---------------------------------------------------------------

FOLDERS = {
    "desktop": "Desktop",
    "documents": "Documents",
    "downloads": "Downloads",
    "pictures": "Pictures",
    "music": "Music",
    "movies": "Movies",
    "videos": "Movies",
    "home": "",
    "applications": "/Applications",
}


def get_folder(name):

    name = name.lower().strip()

    if name not in FOLDERS:
        return None

    value = FOLDERS[name]

    if value.startswith("/"):
        return value

    return str(Path.home() / value) if value else str(Path.home())


def close_finder_folder(path):
    """
    Close the Finder window showing `path`. Returns True if one closed.
    """

    target = os.path.normpath(path).rstrip("/") + "/"

    script = (
        'tell application "Finder"\n'
        "  repeat with w in (every Finder window)\n"
        "    try\n"
        f"      if (POSIX path of (target of w as alias)) is {applescript_string(target)} then\n"
        "        close w\n"
        '        return "closed"\n'
        "      end if\n"
        "    end try\n"
        "  end repeat\n"
        "end tell\n"
        'return ""'
    )

    ok, out = osascript(script)

    return ok and out == "closed"


# ---------------------------------------------------------------
# System controls
# ---------------------------------------------------------------

def get_volume():

    ok, out = osascript("output volume of (get volume settings)")

    try:
        return int(out) if ok else None

    except ValueError:
        return None


def set_volume(level):

    level = max(0, min(int(level), 100))

    ok, _ = osascript(f"set volume output volume {level} without output muted")

    return ok


def change_volume(direction, percent):

    current = get_volume()

    if current is None:
        return False

    delta = percent if direction == "up" else -percent

    return set_volume(current + delta)


def toggle_mute():

    ok, _ = osascript(
        "set volume output muted (not (output muted of (get volume settings)))"
    )

    return ok


# NX_KEYTYPE_* values from IOKit's ev_keymap.h
MEDIA_KEYS = {
    "play_pause": 16,
    "next": 17,
    "previous": 18,
    "stop": 16,
}

BRIGHTNESS_UP = 2
BRIGHTNESS_DOWN = 3


def press_system_key(key_type):
    """
    Send a media or brightness key, as if pressed on an Apple keyboard.
    """

    from AppKit import NSEvent
    import Quartz

    def post(down):

        flags = 0xA00 if down else 0xB00
        data = (key_type << 16) | ((0xA if down else 0xB) << 8)

        event = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            14,  # NSEventTypeSystemDefined
            (0, 0),
            flags,
            0,
            0,
            None,
            8,  # NX_SUBTYPE_AUX_CONTROL_BUTTONS
            data,
            -1,
        )

        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event.CGEvent())

    post(True)
    post(False)


def set_brightness(level):
    """
    Built-in display brightness, in 16 steps like the keyboard keys.
    """

    level = max(0, min(int(level), 100))

    for _ in range(16):
        press_system_key(BRIGHTNESS_DOWN)

    for _ in range(round(level / 100 * 16)):
        press_system_key(BRIGHTNESS_UP)

    return True


class PowerTimer:
    """
    Shutdown and restart wait a while so they can be cancelled, like
    Windows' `shutdown /t 30`.
    """

    def __init__(self):

        self._timer = None
        self._lock = threading.RLock()

    def schedule(self, action, seconds):

        command = {
            "shutdown": 'tell application "System Events" to shut down',
            "restart": 'tell application "System Events" to restart',
        }[action]

        with self._lock:

            self.cancel()

            self._timer = threading.Timer(seconds, lambda: osascript(command, timeout=30))
            self._timer.daemon = True
            self._timer.start()

    def cancel(self):

        with self._lock:

            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
                return True

        return False


POWER = PowerTimer()


def sleep_now():

    subprocess.run(["pmset", "sleepnow"], capture_output=True, text=True)


def lock_screen():
    """
    Lock the Mac (Ctrl+Cmd+Q).
    """

    ok, error = osascript(
        'tell application "System Events" to keystroke "q" using {control down, command down}'
    )

    if not ok:
        raise OSError(error)


def set_dark_mode(dark):

    value = "true" if dark else "false"

    ok, error = osascript(
        'tell application "System Events" to tell appearance preferences '
        f"to set dark mode to {value}"
    )

    if not ok:
        raise OSError(error)


# ---------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------

class Clipboard:

    def get(self):

        result = subprocess.run(["pbpaste"], capture_output=True)

        text = result.stdout.decode("utf-8", errors="replace")

        return text or None

    def set(self, text):

        subprocess.run(["pbcopy"], input=str(text).encode("utf-8"), check=False)


# ---------------------------------------------------------------
# Spotlight
# ---------------------------------------------------------------

def spotlight_query(terms, limit, run=subprocess.run):
    """
    Files whose names contain every term, from the Spotlight index.
    """

    if not terms:
        return []

    query = " && ".join(
        "kMDItemFSName == \"*{}*\"cd".format(t.replace("\\", "").replace('"', ""))
        for t in terms
    )

    result = run(
        ["mdfind", "-onlyin", str(Path.home()), query],
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        raise OSError(result.stderr.strip() or "mdfind failed")

    library = str(Path.home() / "Library") + "/"
    user_files = (library + "CloudStorage/", library + "Mobile Documents/")

    # app data, caches and installed packages are never what people mean
    paths = [
        line for line in result.stdout.splitlines()
        if line.strip()
        and (not line.startswith(library) or line.startswith(user_files))
        and "/node_modules/" not in line
        and "/.git/" not in line
    ]

    # Spotlight does not sort by date; newest first like Windows Search
    def modified(p):

        try:
            return os.path.getmtime(p)

        except OSError:
            return 0

    paths.sort(key=modified, reverse=True)

    return paths[:limit]


# ---------------------------------------------------------------
# Programs
# ---------------------------------------------------------------

def code_signature(path, run=subprocess.run):
    """
    (status, publisher): "signed", "unsigned" or "unknown".
    """

    try:

        result = run(
            ["codesign", "-dv", "--verbose=2", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )

    except Exception:
        return "unknown", ""

    text = (result.stderr or "") + (result.stdout or "")

    if result.returncode != 0:
        return ("unsigned", "") if "not signed" in text else ("unknown", "")

    publisher = ""

    for line in text.splitlines():

        if line.startswith("Authority="):
            publisher = line.split("=", 1)[1]
            break

    for prefix in ("Developer ID Application: ", "Apple Development: "):
        publisher = publisher.removeprefix(prefix)

    return "signed", publisher


def quarantined(path):
    """
    True if macOS marked the file as downloaded from the internet.
    """

    try:

        result = subprocess.run(
            ["xattr", "-p", "com.apple.quarantine", str(path)],
            capture_output=True,
            text=True,
            timeout=5,
        )

    except (OSError, subprocess.TimeoutExpired):
        return None

    return result.returncode == 0


# ---------------------------------------------------------------
# Start at login
# ---------------------------------------------------------------

LAUNCH_AGENT_LABEL = "com.sophia.assistant"


class LaunchAgentAutostart:
    """
    Start Sophia when the user logs in (a per-user LaunchAgent; no
    administrator rights needed).
    """

    def __init__(self, label=LAUNCH_AGENT_LABEL, folder=None, arguments=None):

        self.label = label
        self.folder = Path(folder) if folder else Path.home() / "Library" / "LaunchAgents"
        self.arguments = arguments or self.default_arguments()

    @staticmethod
    def default_arguments():

        main = Path(__file__).resolve().parents[2] / "main.py"

        return [sys.executable, str(main), "--minimized"]

    @property
    def path(self):

        return self.folder / f"{self.label}.plist"

    def is_enabled(self):

        return self.path.exists()

    def enable(self):

        self.folder.mkdir(parents=True, exist_ok=True)

        plist = {
            "Label": self.label,
            "ProgramArguments": [str(a) for a in self.arguments],
            "RunAtLoad": True,
            # a macOS path, whatever system builds it
            "WorkingDirectory": posixpath.dirname(str(self.arguments[1])),
            "ProcessType": "Interactive",
        }

        with open(self.path, "wb") as f:
            plistlib.dump(plist, f)

    def disable(self):

        try:
            self.path.unlink()

        except FileNotFoundError:
            pass

    def set_enabled(self, enabled):

        if enabled:
            self.enable()

        else:
            self.disable()
