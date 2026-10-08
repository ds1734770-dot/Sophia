import json

from app.settings.paths import SUMMARY_FILE


class SummaryStorage:

    FILE = SUMMARY_FILE

    @classmethod
    def load(cls):
        if not cls.FILE.exists():
            return ""

        try:
            with open(cls.FILE, "r", encoding="utf-8") as f:
                return json.load(f)

        except (OSError, ValueError):
            return ""

    @classmethod
    def save(cls, summary):
        with open(cls.FILE, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=4)
