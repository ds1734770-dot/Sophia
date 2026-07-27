import json

from app.settings.paths import APPLICATION_DATABASE


class LaunchHistoryManager:

    def __init__(self):

        self.file = APPLICATION_DATABASE.parent / "launch_history.json"

    # ----------------------------

    def load(self):

        if not self.file.exists():

            return {}

        with open(
            self.file,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    # ----------------------------

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

    # ----------------------------

    def increment(self, app_name):

        data = self.load()

        data[app_name] = data.get(app_name, 0) + 1

        self.save(data)

    # ----------------------------

    def score(self, app_name):

        data = self.load()

        return data.get(app_name, 0)