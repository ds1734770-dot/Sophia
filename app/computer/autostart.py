"""
Start Sophia when the user signs in to Windows (per-user Run key; no
administrator rights needed).
"""

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Sophia"


def default_command():
    """
    The command that launches Sophia: the installed exe, or pythonw
    (no console window) running main.py during development.
    """

    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'

    python = Path(sys.executable)

    pythonw = python.with_name("pythonw.exe")

    if pythonw.exists():
        python = pythonw

    main = Path(__file__).resolve().parents[2] / "main.py"

    return f'"{python}" "{main}" --minimized'


class Autostart:

    def __init__(self, key_path=RUN_KEY, name=VALUE_NAME, command=None):

        self.key_path = key_path
        self.name = name
        self.command = command or default_command()

    def is_enabled(self):

        try:

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.key_path
            ) as key:

                value, _ = winreg.QueryValueEx(key, self.name)

                return bool(value)

        except OSError:
            return False

    def enable(self):

        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, self.key_path
        ) as key:

            winreg.SetValueEx(
                key, self.name, 0, winreg.REG_SZ, self.command
            )

    def disable(self):

        try:

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.key_path,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:

                winreg.DeleteValue(key, self.name)

        except OSError:
            pass

    def set_enabled(self, enabled):

        if enabled:
            self.enable()

        else:
            self.disable()
