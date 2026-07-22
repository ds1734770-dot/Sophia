import json
from pathlib import Path


class SummaryStorage:

    FILE = Path("summary.json")

    @classmethod
    def load(cls):
        if not cls.FILE.exists():
            return ""

        with open(cls.FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def save(cls, summary):
        with open(cls.FILE, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=4)