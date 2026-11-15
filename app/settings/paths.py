import os
import sys
from pathlib import Path

# Sophia Project Root
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _data_dir():
    """
    Wherever SOPHIA_HOME says; otherwise the system's place for app data,
    never the code folder (an update must not touch it, and the code may
    be shared between computers through a synced folder):

        Windows   %APPDATA%\\Sophia
        macOS     ~/Library/Application Support/Sophia
    """

    override = os.getenv("SOPHIA_HOME")

    if override:
        return Path(override)

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Sophia"

    if sys.platform == "win32":
        return Path(os.getenv("APPDATA") or Path.home()) / "Sophia"

    return PROJECT_ROOT / "data"


def _move_old_data(new):
    """
    Older versions kept their data in data/ next to the code, where an
    update could touch it. Copy it to the new folder once (data/ is left
    as it was).
    """

    old = PROJECT_ROOT / "data"

    if os.getenv("SOPHIA_HOME") or new == old or not old.is_dir():
        return

    marker = new / ".copied-from-project"

    if marker.exists() or any(new.glob("*.json")):
        return

    try:

        import shutil

        new.mkdir(parents=True, exist_ok=True)

        # the Mac copies personal files in its setup script; elsewhere
        # everything comes along (history, notes, models, logs)
        if sys.platform != "darwin":
            shutil.copytree(old, new, dirs_exist_ok=True)

        marker.write_text(str(old), encoding="utf-8")

    except OSError:
        pass


# ------------------------
# Data
# ------------------------

DATA_DIR = _data_dir()

_move_old_data(DATA_DIR)

PROFILE_FILE = DATA_DIR / "profile.json"

MEMORY_FILE = DATA_DIR / "memories.json"

FILE_DATABASE = DATA_DIR / "file_database.json"

SCHEDULE_FILE = DATA_DIR / "schedules.json"

USAGE_FILE = DATA_DIR / "usage.json"

SUMMARY_FILE = DATA_DIR / "summary.json"

APPLICATION_DATABASE = DATA_DIR / "applications.json"

# ------------------------
# Future
# ------------------------

CACHE_DIR = DATA_DIR / "cache"

LOGS_DIR = DATA_DIR / "logs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
