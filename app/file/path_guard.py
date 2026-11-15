"""
Where Sophia may read and change files.

Reading is allowed almost everywhere on the PC, except places that hold
secrets (SSH keys, saved passwords, browser cookies...), because file
contents can be sent to the AI.

Changing files is allowed in the user's own files on any drive, but never
in Windows itself, installed programs, AppData, or Sophia's own folder.
"""

import os
import sys
from collections.abc import Iterable
from pathlib import Path

IS_MAC = sys.platform == "darwin"

# Files Sophia must never open: opening these runs code.
EXECUTABLE_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".psm1", ".vbs",
    ".vbe", ".js", ".jse", ".wsf", ".scr", ".lnk", ".reg", ".dll", ".jar",
    # macOS
    ".app", ".command", ".sh", ".zsh", ".bash", ".tool", ".scpt",
    ".applescript", ".workflow", ".pkg", ".mpkg", ".dylib", ".kext",
    ".terminal", ".webloc", ".inetloc",
}

# Folder names that hold credentials
SECRET_DIRS = {
    ".ssh", ".aws", ".gnupg", ".azure", ".kube", ".docker", "credentials",
    "protect", "vault", "keychains", "1password",
}

# File names and endings that are secrets
SECRET_NAMES = {
    "id_rsa", "id_ed25519", "id_ecdsa", "login data", "cookies",
    "web data", "key3.db", "key4.db", "logins.json", "ntuser.dat",
    "cookies.binarycookies", "login.keychain-db", ".netrc", ".zsh_history",
    ".bash_history",
}
SECRET_SUFFIXES = {".pem", ".pfx", ".p12", ".key", ".kdbx", ".ppk"}

# Never offered in search results
JUNK_DIRS = {
    "node_modules", ".git", "__pycache__", "site-packages", ".venv", "venv",
    ".cache", "$recycle.bin", "system volume information", ".next",
    ".gradle", ".idea", ".vscode", "dist", "build", ".trash", ".spotlight-v100",
    ".fseventsd",
}

# macOS: the system, installed apps and Unix tools
MAC_SYSTEM_DIRS = [
    "/System", "/Library", "/Applications", "/usr", "/bin", "/sbin",
    "/private/etc", "/private/var/db", "/private/var/root", "/opt", "/cores",
]


def default_system_dirs() -> list[Path]:

    if IS_MAC:
        return [Path(d) for d in MAC_SYSTEM_DIRS]

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

    def __init__(
        self,
        home: str | Path | None = None,
        system_dirs: Iterable[str | Path] | None = None,
        protected: Iterable[str | Path] | None = None,
    ) -> None:

        self.home = Path(home) if home else Path.home()

        self.system_dirs = [
            Path(d) for d in (
                default_system_dirs() if system_dirs is None else system_dirs
            )
        ]

        # Never changed: AppData, plus anything passed in (Sophia's
        # own folder, so it cannot delete itself)
        mac = IS_MAC and home is None

        self._app_data = self.home / ("Library" if mac else "AppData")

        self.protected = [self._app_data] + [Path(p) for p in (protected or [])]

        # On macOS, Google Drive, Dropbox, OneDrive and iCloud Drive keep
        # the user's own files inside ~/Library
        self.user_files_in_app_data = [
            self.home / "Library" / "CloudStorage",
            self.home / "Library" / "Mobile Documents",
        ] if mac else []

    # ------------------------------------------------

    @staticmethod
    def _resolve(path: str | Path) -> Path | None:

        try:
            return Path(path).expanduser().resolve()

        except (OSError, ValueError):
            return None

    @staticmethod
    def _within(path: Path, folder: Path) -> bool:

        try:
            folder = folder.resolve()

        except OSError:
            return False

        return path == folder or folder in path.parents

    def is_secret(self, path: Path) -> bool:

        parts = {p.lower() for p in path.parts}

        if parts & SECRET_DIRS:
            return True

        name = path.name.lower()

        return name in SECRET_NAMES or path.suffix.lower() in SECRET_SUFFIXES

    def is_junk(self, path: Path) -> bool:

        return bool({p.lower() for p in path.parts} & JUNK_DIRS)

    # ------------------------------------------------

    def for_read(self, path: str | Path) -> Path | None:
        """
        The resolved Path if Sophia may read it, else None.
        """

        resolved = self._resolve(path)

        if resolved is None or self.is_secret(resolved):
            return None

        return resolved

    def for_write(self, path: str | Path) -> Path | None:
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

            if self._within(resolved, folder) and not self._user_file(resolved, folder):
                return None

        return resolved

    def _user_file(self, resolved: Path, folder: Path) -> bool:
        """
        True for cloud-drive files that only look like app data.
        """

        return folder == self._app_data and any(
            self._within(resolved, f) for f in self.user_files_in_app_data
        )

    def why_not_write(self, path: str | Path) -> str:
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
                return (
                    "That is part of macOS or installed apps." if IS_MAC
                    else "That is part of Windows or installed programs."
                )

        for folder in self.protected:

            if self._within(resolved, folder) and not self._user_file(resolved, folder):
                return (
                    "That folder is protected (Library or Sophia's own files)." if IS_MAC
                    else "That folder is protected (AppData or Sophia's own files)."
                )

        return "That location is not allowed."


def allowed_roots(home: str | Path | None = None) -> list[Path]:
    """
    The everyday folders, for names like "Desktop" or "Documents".
    """

    home = Path(home) if home else Path.home()

    return [home / "Desktop", home / "Documents", home / "Downloads"]


def is_safe_name(name: str) -> bool:
    """
    A plain file or folder name: no separators, no parent references.
    """

    if not name or name in (".", ".."):
        return False

    if any(sep in name for sep in ("/", "\\", ":")):
        return False

    return name == name.strip() and not name.endswith(".")
