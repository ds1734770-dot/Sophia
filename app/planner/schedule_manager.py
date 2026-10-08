import json
from app.settings.paths import SCHEDULE_FILE


class ScheduleManager:

    def __init__(self):
        self.file = SCHEDULE_FILE
        self.schedules = self.load()

    def load(self):
        if not self.file.exists():
            return {}

        try:
            with open(self.file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(
                self.schedules,
                f,
                indent=4
            )

    def add_schedule(self, date, time, task):

        if date not in self.schedules:
            self.schedules[date] = []

        self.schedules[date].append(
            {
                "time": time,
                "task": task
            }
        )

        self.schedules[date].sort(
            key=lambda x: x["time"]
        )

        self.save()

    def get_schedule(self, date):
        return self.schedules.get(date, [])

    def delete_schedule(self, date):

        if date in self.schedules:
            del self.schedules[date]
            self.save()