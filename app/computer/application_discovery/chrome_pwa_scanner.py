from pathlib import Path

from app.computer.application_normalizer import ApplicationNormalizer


class ChromePWAScanner:

    def __init__(self):

        self.normalizer = ApplicationNormalizer()

        self.root = (
            Path.home()
            / "AppData"
            / "Local"
            / "Google"
            / "Chrome"
            / "User Data"
            / "Default"
            / "Web Applications"
        )

    def scan(self):

        applications = []

        if not self.root.exists():
            return applications

        for shortcut in self.root.rglob("*.lnk"):

            applications.append({

                "name": shortcut.stem,

                "aliases": self.normalizer.aliases(shortcut.stem),

                "shortcut": str(shortcut),

                "type": "chrome_pwa",

            })

        return applications