"""
Windows built-in apps that live in System32 and have no Start Menu
or registry entry, so the normal discovery never finds them.
"""

import sys

BUILTIN_APPS = [
    ("Notepad", "notepad.exe", ["notepad"]),
    ("Calculator", "calc.exe", ["calculator", "calc"]),
    ("Paint", "mspaint.exe", ["paint", "mspaint"]),
    ("Command Prompt", "cmd.exe", ["cmd", "command prompt"]),
    ("Windows PowerShell", "powershell.exe", ["powershell"]),
    ("File Explorer", "explorer.exe", ["file explorer", "explorer"]),
    ("Task Manager", "taskmgr.exe", ["task manager", "taskmgr"]),
    ("Snipping Tool", "snippingtool.exe", ["snipping tool", "snip"]),
    ("Control Panel", "control.exe", ["control panel"]),
    ("Windows Terminal", "wt.exe", ["terminal", "windows terminal"]),
]

# Opened through the shell instead of as a program
BUILTIN_SHELL_TARGETS = [
    ("Settings", "ms-settings:", ["settings", "windows settings"]),
]


# Programs whose running process has a different name than the launcher
PROCESS_NAMES = {
    "Calculator": "CalculatorApp.exe",
    "Snipping Tool": "SnippingTool.exe",
}


# macOS: Windows names people still say, pointed at the Mac app that does
# the same job (discovery finds the apps themselves)
MAC_ALIASES = [
    ("TextEdit", "/System/Applications/TextEdit.app", ["notepad", "text editor", "textedit"]),
    ("Calculator", "/System/Applications/Calculator.app", ["calculator", "calc"]),
    ("Terminal", "/System/Applications/Utilities/Terminal.app", ["terminal", "cmd", "command prompt", "powershell", "shell"]),
    ("Finder", "/System/Library/CoreServices/Finder.app", ["finder", "file explorer", "explorer", "files"]),
    ("Activity Monitor", "/System/Applications/Utilities/Activity Monitor.app", ["activity monitor", "task manager", "taskmgr"]),
    ("Screenshot", "/System/Applications/Utilities/Screenshot.app", ["snipping tool", "snip", "screenshot"]),
    ("System Settings", "/System/Applications/System Settings.app", ["settings", "system settings", "control panel", "system preferences"]),
    ("Preview", "/System/Applications/Preview.app", ["preview", "photos viewer", "pdf viewer"]),
]


def mac_builtin_applications():

    apps = []

    for name, path, aliases in MAC_ALIASES:
        apps.append({
            "name": name,
            "aliases": aliases,
            "app": path,
            "process": name,
            "type": "builtin",
        })

    return apps


def builtin_applications():
    """
    Records in the same shape as the discovered applications.
    """

    if sys.platform == "darwin":
        return mac_builtin_applications()

    apps = []

    for name, exe, aliases in BUILTIN_APPS:
        apps.append({
            "name": name,
            "aliases": aliases,
            "exe": exe,
            "process": PROCESS_NAMES.get(name),
            "type": "builtin",
        })

    for name, target, aliases in BUILTIN_SHELL_TARGETS:
        apps.append({
            "name": name,
            "aliases": aliases,
            "shortcut": target,
            "type": "builtin",
        })

    return apps


def merge_builtin(applications):
    """
    Add built-in apps that discovery did not already find.
    """

    known = {app["name"].lower() for app in applications}

    builtin = builtin_applications()

    if sys.platform == "darwin":

        # discovery already has these apps; add the familiar Windows
        # names to them instead of listing each app twice
        extra_aliases = {app["name"].lower(): app["aliases"] for app in builtin}

        merged = []

        for app in applications:

            more = extra_aliases.get(app["name"].lower())

            if more:
                app = dict(app, aliases=list(dict.fromkeys(list(app.get("aliases") or []) + more)))

            merged.append(app)

        applications = merged

    extra = [
        app for app in builtin
        if app["name"].lower() not in known
    ]

    return list(applications) + extra
