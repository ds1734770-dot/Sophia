"""
Where Sophia may read and change files.

Reading is allowed almost everywhere on the PC, except places that hold
secrets (SSH keys, saved passwords, browser cookies...), because file
contents can be sent to the AI.

Changing files is allowed in the user's own files on any drive, but never
in Windows itself, installed programs, AppData, or Sophia's own folder.
"""

import os
from pathlib import Path

# Files Sophia must never open: opening these runs code.
EXECUTABLE_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".psm1", ".vbs",
    ".vbe", ".js", ".jse", ".wsf", ".scr", ".lnk", ".reg", ".dll", ".jar",
}

# Folder names that hold credentials
SECRET_DIRS = {
    ".ssh", ".aws", ".gnupg", ".azure", ".kube", ".docker", "credentials",
    "protect", "vault",
}

# File names and endings that are secrets
SECRET_NAMES = {
    "id_rsa", "id_ed25519", "id_ecdsa", "login data", "cookies",
    "web data", "key3.db", "key4.db", "logins.json", "ntuser.dat",
}
SECRET_SUFFIXES = {".pem", ".pfx", ".p12", ".key", ".kdbx", ".ppk"}

# Never offered in search results
JUNK_DIRS = {
    "node_modules", ".git", "__pycache__", "site-packages", ".venv", "venv",
    ".cache", "$recycle.bin", "system volume information", ".next",
    ".gradle", ".idea", ".vscode", "dist", "build",
}


def default_system_dirs():

    dirs = []

    for variable in (
        "SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData",
        "ProgramW6432",
    ):

        value = os.getenv(variable)

        if value:
            dirs.append(Path(value))

    return dirs


class PathGuard:

    def __init__(self, home=None, system_dirs=None, protected=None):

        self.home = Path(home) if home else Path.home()

        self.system_dirs = [
            Path(d) for d in (
                default_system_dirs() if system_dirs is None else system_dirs
            )
        ]

        # Never changed: AppData, plus anything passed in (Sophia's
        # own folder, so it cannot delete itself)
        self.protected = [self.home / "AppData"] + [Path(p) for p in (protected or [])]

    # ------------------------------------------------

    @staticmethod
    def _resolve(path):

        try:
            return Path(path).expanduser().resolve()

        except (OSError, ValueError):
            return None

    @staticmethod
    def _within(path, folder):

        try:
            folder = folder.resolve()

        except OSError:
            return False

        return path == folder or folder in path.parents

    def is_secret(self, path):

        parts = {p.lower() for p in path.parts}

        if parts & SECRET_DIRS:
            return True

        name = path.name.lower()

        return name in SECRET_NAMES or path.suffix.lower() in SECRET_SUFFIXES

    def is_junk(self, path):

        return bool({p.lower() for p in path.parts} & JUNK_DIRS)

    # ------------------------------------------------

    def for_read(self, path):
        """
        The resolved Path if Sophia may read it, else None.
        """

        resolved = self._resolve(path)

        if resolved is None or self.is_secret(resolved):
            return None

        return resolved

    def for_write(self, path):
        """
        The resolved Path if Sophia may change it, else None.
        """

        resolved = self._resolve(path)

        if resolved is None or self.is_secret(resolved):
            return None

        # Drive roots and the home folder itself
        if resolved == Path(resolved.anchor) or resolved == self.home.resolve():
            return None

        for folder in self.system_dirs + self.protected:

            if self._within(resolved, folder):
                return None

        return resolved

    def why_not_write(self, path):
        """
        A short reason a path is off limits, for error messages.
        """

        resolved = self._resolve(path)

        if resolved is None:
            return "That is not a valid path."

        if self.is_secret(resolved):
            return "That looks like a credentials or key file."

        for folder in self.system_dirs:

            if self._within(resolved, folder):
                return "That is part of Windows or installed programs."

        for folder in self.protected:

            if self._within(resolved, folder):
                return "That folder is protected (AppData or Sophia's own files)."

        return "That location is not allowed."


def allowed_roots(home=None):
    """
    The everyday folders, for names like "Desktop" or "Documents".
    """

    home = Path(home) if home else Path.home()

    return [home / "Desktop", home / "Documents", home / "Downloads"]


def is_safe_name(name):
    """
    A plain file or folder name: no separators, no parent references.
    """

    if not name or name in (".", ".."):
        return False

    if any(sep in name for sep in ("/", "\\", ":")):
        return False

    return name == name.strip() and not name.endswith(".")
