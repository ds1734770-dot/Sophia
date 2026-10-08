import os
import sys
from pathlib import Path

# Sophia Project Root
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _data_dir():
    """
    Next to the code while developing; in the APPDATA Sophia folder when
    installed (the install folder is not writable), or wherever
    SOPHIA_HOME says.
    """

    override = os.getenv("SOPHIA_HOME")

    if override:
        return Path(override)

    if getattr(sys, "frozen", False):
        return Path(os.getenv("APPDATA") or Path.home()) / "Sophia"

    return PROJECT_ROOT / "data"


# ------------------------
# Data
# ------------------------

DATA_DIR = _data_dir()

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
