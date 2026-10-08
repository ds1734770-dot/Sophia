"""
Model pool: spreads requests over several Gemini models so one model's
quota (or an outage) does not stop Sophia.

Each model has its own free-tier quota. When a model fails with a quota
or availability error it "cools down" for a while and the next model in
the list is used. Cooldowns are remembered, so later messages skip a dead
model at once instead of waiting for it to time out.
"""

import json
import re
import time
from datetime import date

# Quota/availability errors: try another model
QUOTA_MARKERS = ("429", "RESOURCE_EXHAUSTED")
SERVER_MARKERS = ("500", "503", "504", "INTERNAL", "UNAVAILABLE", "DEADLINE_EXCEEDED")
GONE_MARKERS = ("404", "NOT_FOUND")

DEFAULT_COOLDOWN = 60
SERVER_COOLDOWN = 90
DAILY_COOLDOWN = 3600
GONE_COOLDOWN = 6 * 3600
MAX_QUOTA_WAIT = 600


def classify(error_text):
    """
    Return (kind, cooldown_seconds) for an error, or (None, 0) if the
    error is not the model's fault (bad request, auth...) and switching
    models would not help.
    """

    text = error_text

    if any(m in text for m in QUOTA_MARKERS):

        if "PerDay" in text or "per day" in text.lower():
            return "quota", DAILY_COOLDOWN

        match = re.search(r"retry(?: in|Delay\D{0,4})\s*([\d.]+)\s*s", text)

        if match:
            return "quota", min(float(match.group(1)) + 1, MAX_QUOTA_WAIT)

        return "quota", DEFAULT_COOLDOWN

    if any(m in text for m in GONE_MARKERS):
        return "gone", GONE_COOLDOWN

    if any(m in text for m in SERVER_MARKERS) or "timed out" in text.lower():
        return "server", SERVER_COOLDOWN

    return None, 0


class ModelPool:

    def __init__(self, models, clock=time.monotonic, usage=None):

        self.models = list(dict.fromkeys(m for m in models if m))
        self.clock = clock
        self.usage = usage

        self.cooldown_until = {}

    # ------------------------------------------------

    def available(self, models=None):
        """
        Models that are not cooling down, in priority order.
        """

        now = self.clock()

        return [
            m for m in (models or self.models)
            if self.cooldown_until.get(m, 0) <= now
        ]

    def soonest_wait(self, models=None):
        """
        Seconds until some model is usable again (0 if one is).
        """

        now = self.clock()

        waits = [
            max(0.0, self.cooldown_until.get(m, 0) - now)
            for m in (models or self.models)
        ]

        return min(waits) if waits else 0.0

    def mark_failed(self, model, error_text):
        """
        Record a failure. Returns the error kind, or None when the error
        is not about the model (nothing is marked).
        """

        kind, seconds = classify(error_text)

        if kind is None:
            return None

        self.cooldown_until[model] = self.clock() + seconds

        if self.usage is not None:
            self.usage.record(model, kind)

        return kind

    def mark_ok(self, model):

        self.cooldown_until.pop(model, None)

        if self.usage is not None:
            self.usage.record(model, "ok")


class UsageTracker:
    """
    Counts requests per model per day (data/usage.json) so quota use can
    be seen and tuned. Never raises: usage tracking must not break chat.
    """

    def __init__(self, path):

        self.path = path

    def _load(self):

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)

        except (OSError, ValueError):
            return {}

    def record(self, model, outcome):

        try:

            data = self._load()

            today = date.today().isoformat()

            # keep a week
            for day in sorted(data)[:-6]:
                data.pop(day, None)

            counts = data.setdefault(today, {}).setdefault(model, {})
            counts[outcome] = counts.get(outcome, 0) + 1

            self.path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        except Exception:
            pass

    def today(self):

        return self._load().get(date.today().isoformat(), {})

    def report(self):

        today = self.today()

        if not today:
            return "No AI requests yet today."

        lines = ["AI requests today:"]

        for model, counts in today.items():

            detail = ", ".join(f"{k}: {v}" for k, v in counts.items())

            lines.append(f"- {model}: {detail}")

        return "\n".join(lines)
