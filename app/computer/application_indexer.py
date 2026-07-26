import json
from pathlib import Path
import os
from app.settings.paths import APPLICATION_DATABASE
from app.computer.application_normalizer import ApplicationNormalizer


class ApplicationIndexer:

    def __init__(self):

        self.database = APPLICATION_DATABASE
        self.normalizer = ApplicationNormalizer()
        

        self.search_locations = [

            Path(os.environ["APPDATA"])
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs",

            Path(os.environ["ProgramData"])
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs",

        ]

    # ----------------------------

    def build(self):

        applications = []

        for root in self.search_locations:

            if not root.exists():
                continue

            for shortcut in root.rglob("*.lnk"):

                applications.append({
                    "name": shortcut.stem,
                    "aliases": self.normalizer.aliases(shortcut.stem) or [],
                    "shortcut": str(shortcut),
                    "type": "shortcut"
                })

        return applications
    # ----------------------------

    def save(self):

        apps = self.build()

        self.database.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(
            self.database,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                apps,
                f,
                indent=4
            )

        return len(apps)
    # ----------------------------

    def load(self):

        if not self.database.exists():
            return []

        with open(
            self.database,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    # ----------------------------

    # def search(self, name):

    #     applications = self.load()

    #     name = name.lower().strip()

    #     results = []

    #     # Exact Match
    #     for app in applications:

    #         if app["name"].lower() == name:

    #             return True, [app]

    #     # Partial Match
    #     for app in applications:

    #         if name in app["name"].lower():

    #             results.append(app)

    #     if results:

    #         return True, results

    #     return False, "No matching applications found."