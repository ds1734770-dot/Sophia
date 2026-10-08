from pathlib import Path

# Files Sophia must never open: opening these runs code.
EXECUTABLE_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".psm1", ".vbs",
    ".vbe", ".js", ".jse", ".wsf", ".scr", ".lnk", ".reg", ".dll", ".jar",
}


def allowed_roots(home=None):
    """
    Folders Sophia may read from and change.
    """

    home = Path(home) if home else Path.home()

    return [home / "Desktop", home / "Documents", home / "Downloads"]


def resolve_allowed(path, home=None):
    """
    Return the resolved Path if it is inside an allowed folder
    (and not an allowed root itself), otherwise None.

    Resolving first defeats "..\\" tricks and symlinks that point
    outside the allowed folders.
    """

    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, ValueError):
        return None

    for root in allowed_roots(home):

        root = root.resolve()

        if resolved != root and root in resolved.parents:
            return resolved

    return None


def is_safe_name(name):
    """
    A plain file or folder name: no separators, no parent references.
    """

    if not name or name in (".", ".."):
        return False

    if any(sep in name for sep in ("/", "\\", ":")):
        return False

    return name == name.strip() and not name.endswith(".")
