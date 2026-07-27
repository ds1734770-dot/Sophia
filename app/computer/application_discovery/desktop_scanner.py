from pathlib import Path

from app.computer.application_normalizer import ApplicationNormalizer


class DesktopScanner:

    def __init__(self):

        self.normalizer = ApplicationNormalizer()

        self.desktop_locations = [

            # Current User Desktop
            Path.home() / "Desktop",

            # OneDrive Desktop
            Path.home() / "OneDrive" / "Desktop",

            # Public Desktop
            Path(r"C:\Users\Public\Desktop"),

        ]

    def scan(self):

        applications = []

        for desktop in self.desktop_locations:

            if not desktop.exists():
                continue

            for shortcut in desktop.glob("*.lnk"):

                applications.append({

                    "name": shortcut.stem,

                    "aliases": self.normalizer.aliases(shortcut.stem),

                    "shortcut": str(shortcut),

                    "type": "desktop",

                })

        return applications