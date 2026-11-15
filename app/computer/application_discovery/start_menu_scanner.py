import os
from pathlib import Path

from app.computer.application_normalizer import ApplicationNormalizer


class StartMenuScanner:

    def __init__(self):

        self.normalizer = ApplicationNormalizer()

        self.search_locations = [

            Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs",

            Path(os.environ.get("ProgramData", "C:/ProgramData"))
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs",

        ]

    def scan(self):

        applications = []

        for root in self.search_locations:

            if not root.exists():
                continue

            for shortcut in root.rglob("*.lnk"):

                applications.append({

                    "name": shortcut.stem,

                    "aliases": self.normalizer.aliases(shortcut.stem) or [],

                    "shortcut": str(shortcut),

                    "type": "shortcut",

                })

        return applications