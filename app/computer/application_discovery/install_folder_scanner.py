from pathlib import Path

from app.computer.application_normalizer import ApplicationNormalizer


class InstallFolderScanner:

    def __init__(self):

        self.normalizer = ApplicationNormalizer()

        self.search_locations = [

            Path(r"C:\Program Files"),

            Path(r"C:\Program Files (x86)"),

            Path.home() / "AppData" / "Local",

        ]

        self.blacklist = {

            "uninstall",
            "setup",
            "update",
            "updater",
            "helper",
            "crashpad",
            "installer",
            "repair",

        }

    def scan(self):

        applications = []

        for root in self.search_locations:

            if not root.exists():
                continue

            for exe in root.rglob("*.exe"):

                name = exe.stem.lower()

                if any(word in name for word in self.blacklist):
                    continue

                applications.append({

                    "name": exe.stem,

                    "aliases": self.normalizer.aliases(exe.stem),

                    "exe": str(exe),

                    "type": "install_folder",

                })

        return applications