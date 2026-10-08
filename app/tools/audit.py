"""
A record of everything Sophia did on the computer: data/logs/actions.jsonl,
one JSON object per line. Never raises; never stores file contents.
"""

import json
import logging
from datetime import datetime

log = logging.getLogger("sophia.audit")

MAX_VALUE_CHARS = 300


def _short(value):

    text = str(value)

    if len(text) > MAX_VALUE_CHARS:
        return text[:MAX_VALUE_CHARS] + "..."

    return text


class AuditLog:

    def __init__(self, path):

        self.path = path

    def __call__(self, name, args, result, confirmed):

        try:

            entry = {
                "time": datetime.now().isoformat(timespec="seconds"),
                "tool": name,
                "args": {k: _short(v) for k, v in args.items()},
                "ok": result.ok,
                "confirmed": bool(confirmed),
                "result": _short(result.message),
            }

            self.path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        except Exception as e:

            log.warning("Could not write the action log: %s", e)

    def recent(self, count=20):

        try:

            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-count:]

            return [json.loads(line) for line in lines]

        except (OSError, ValueError):
            return []
