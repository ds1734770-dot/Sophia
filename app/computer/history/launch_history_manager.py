import json
from datetime import datetime

from app.settings.paths import APPLICATION_DATABASE


class LaunchHistoryManager:

    def __init__(self):

        self.file = APPLICATION_DATABASE.parent / "launch_history.json"

    # ------------------------------------------------

    def load(self):

        if not self.file.exists():

            return {}

        with open(
            self.file,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    # ------------------------------------------------

    def save(self, data):

        with open(
            self.file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                indent=4
            )

    # ------------------------------------------------

    def increment(self, app_name):

        data = self.load()

        if app_name not in data:

            data[app_name] = {
                "count": 0,
                "last_used": "",
                "favorite": False
            }

        data[app_name]["count"] += 1
        data[app_name]["last_used"] = datetime.now().isoformat()

        self.save(data)

    # ------------------------------------------------

    def set_favorite(self, app_name, value=True):

        data = self.load()

        if app_name not in data:

            data[app_name] = {
                "count": 0,
                "last_used": "",
                "favorite": value
            }

        data[app_name]["favorite"] = value

        self.save(data)

    # ------------------------------------------------

    def score(self, app_name):

        data = self.load()

        if app_name not in data:

            return 0

        app = data[app_name]

        score = 0

        # --------------------------
        # Frequency
        # --------------------------

        score += min(app["count"], 30)

        # --------------------------
        # Favorite
        # --------------------------

        if app.get("favorite", False):

            score += 30

        # --------------------------
        # Recent Usage
        # --------------------------

        if app.get("last_used"):

            try:

                last_used = datetime.fromisoformat(
                    app["last_used"]
                )

                hours = (
                    datetime.now() - last_used
                ).total_seconds() / 3600

                if hours <= 1:

                    score += 20

                elif hours <= 24:

                    score += 10

                elif hours <= 168:

                    score += 5

            except Exception:

                pass

        return score