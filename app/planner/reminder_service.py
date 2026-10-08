"""
Makes Sophia proactive: a background loop that fires schedule entries,
timers and recurring routines at the right time and tells the user
(pop-up, voice, chat) without being asked.
"""

import json
import logging
import threading
from datetime import datetime, timedelta

log = logging.getLogger("sophia.reminders")

# An entry whose time passed more than this long ago is marked as seen
# silently (Sophia was closed when it was due) instead of alerting late.
MISSED_AFTER = timedelta(minutes=60)

# A routine missed by more than this today is skipped until tomorrow
ROUTINE_GRACE = timedelta(hours=3)

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class JsonStore:
    """
    A small JSON file holding one list or dict; never raises on read.
    """

    def __init__(self, path, default):

        self.path = path
        self.default = default

        self.data = self._load()

    def _load(self):

        try:

            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)

        except (OSError, ValueError):
            return self.default()

    def save(self):

        self.path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)


class TimerStore(JsonStore):

    def __init__(self, path):

        super().__init__(path, list)

        self._next = max((t["id"] for t in self.data), default=0) + 1

    def add(self, due, label):

        timer = {"id": self._next, "due": due.isoformat(timespec="seconds"), "label": label}

        self._next += 1
        self.data.append(timer)
        self.save()

        return timer

    def cancel(self, timer_id):

        before = len(self.data)

        self.data = [t for t in self.data if t["id"] != timer_id]
        self.save()

        return len(self.data) < before

    def due(self, now):

        return [t for t in self.data if datetime.fromisoformat(t["due"]) <= now]

    def remove_all(self, timers):

        ids = {t["id"] for t in timers}

        self.data = [t for t in self.data if t["id"] not in ids]
        self.save()


class RoutineStore(JsonStore):
    """
    Recurring tasks: {id, name, time "HH:MM", days [0-6], kind, text,
    last_run}. kind "reminder" just alerts with `text`; kind "prompt"
    asks Sophia to do `text` and shows the answer.
    """

    def __init__(self, path):

        super().__init__(path, list)

        self._next = max((r["id"] for r in self.data), default=0) + 1

    def add(self, name, at, days, kind, text):

        routine = {
            "id": self._next,
            "name": name,
            "time": at,
            "days": days,
            "kind": kind,
            "text": text,
            "last_run": None,
        }

        self._next += 1
        self.data.append(routine)
        self.save()

        return routine

    def remove(self, routine_id):

        before = len(self.data)

        self.data = [r for r in self.data if r["id"] != routine_id]
        self.save()

        return len(self.data) < before


class FiredStore(JsonStore):
    """
    Which schedule entries have already alerted (keyed by date, time and
    task).
    """

    def __init__(self, path):

        super().__init__(path, list)

    @staticmethod
    def key(date, at, task):

        return f"{date}|{at}|{task}"

    def has(self, key):

        return key in self.data

    def add(self, key):

        self.data.append(key)

        # keep the file small
        self.data = self.data[-500:]
        self.save()


def parse_days(text):
    """
    "daily", "weekdays", "weekends" or names like "mon,wed,fri" -> list
    of weekday numbers (Monday is 0). Returns None if not understood.
    """

    text = (text or "daily").strip().lower()

    if text in ("daily", "every day", "everyday", ""):
        return list(range(7))

    if text in ("weekdays", "weekday"):
        return [0, 1, 2, 3, 4]

    if text in ("weekends", "weekend"):
        return [5, 6]

    days = []

    for part in text.replace(" ", "").split(","):

        if part[:3] in DAY_NAMES:
            days.append(DAY_NAMES.index(part[:3]))

        else:
            return None

    return sorted(set(days)) or None


class ReminderService:

    def __init__(
        self,
        planner,
        timers,
        routines,
        fired,
        notify,
        run_prompt=None,
        clock=datetime.now,
        interval=15,
    ):

        self.planner = planner
        self.timers = timers
        self.routines = routines
        self.fired = fired

        self.notify = notify
        self.run_prompt = run_prompt

        self.clock = clock
        self.interval = interval

        self._stop = threading.Event()
        self._thread = None

    # ------------------------------------------------

    def start(self):

        if self._thread is not None:
            return

        self._thread = threading.Thread(
            target=self._run, name="reminders", daemon=True
        )

        self._thread.start()

    def stop(self):

        self._stop.set()

    def _run(self):

        while not self._stop.is_set():

            try:
                self.tick(self.clock())

            except Exception:
                log.exception("Reminder check failed")

            self._stop.wait(self.interval)

    # ------------------------------------------------

    def tick(self, now):
        """
        Fire everything that is due at `now`. Returns the number of
        alerts sent (also used by tests).
        """

        sent = 0

        sent += self._agenda(now)
        sent += self._timers(now)
        sent += self._routines(now)

        return sent

    def _agenda(self, now):

        today = now.strftime("%Y-%m-%d")

        sent = 0

        for entry in self.planner.get_schedule(today):

            key = self.fired.key(today, entry["time"], entry["task"])

            if self.fired.has(key):
                continue

            try:

                due = datetime.strptime(f"{today} {entry['time']}", "%Y-%m-%d %H:%M")

            except ValueError:
                continue

            if due > now:
                continue

            self.fired.add(key)

            if now - due > MISSED_AFTER:
                continue

            self.notify("Reminder", f"{entry['time']} {entry['task']}")

            sent += 1

        return sent

    def _timers(self, now):

        due = self.timers.due(now)

        if not due:
            return 0

        self.timers.remove_all(due)

        for timer in due:
            self.notify("Timer", f"Time's up: {timer['label']}")

        return len(due)

    def _routines(self, now):

        sent = 0

        today = now.strftime("%Y-%m-%d")

        for routine in list(self.routines.data):

            if routine["last_run"] == today or now.weekday() not in routine["days"]:
                continue

            hour, minute = (int(x) for x in routine["time"].split(":"))

            scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if scheduled > now:
                continue

            routine["last_run"] = today
            self.routines.save()

            if now - scheduled > ROUTINE_GRACE:
                continue

            if routine["kind"] == "prompt" and self.run_prompt is not None:

                try:
                    text = self.run_prompt(routine["text"])

                except Exception as e:

                    log.warning("Routine %s failed: %s", routine["name"], e)
                    continue

            else:
                text = routine["text"]

            self.notify(routine["name"], text)

            sent += 1

        return sent
