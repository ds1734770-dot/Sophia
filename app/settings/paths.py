from pathlib import Path

# Sophia Project Root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# ------------------------
# Data
# ------------------------

DATA_DIR = PROJECT_ROOT / "data"

PROFILE_FILE = DATA_DIR / "profile.json"

MEMORY_FILE = DATA_DIR / "memories.json"

FILE_DATABASE = DATA_DIR / "file_database.json"

APPLICATION_DATABASE = DATA_DIR / "applications.json"

# ------------------------
# Future
# ------------------------

CACHE_DIR = DATA_DIR / "cache"

LOGS_DIR = DATA_DIR / "logs"