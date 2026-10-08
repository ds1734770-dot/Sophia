"""
Windows built-in apps that live in System32 and have no Start Menu
or registry entry, so the normal discovery never finds them.
"""

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


def builtin_applications():
    """
    Records in the same shape as the discovered applications.
    """

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

    extra = [
        app for app in builtin_applications()
        if app["name"].lower() not in known
    ]

    return list(applications) + extra
