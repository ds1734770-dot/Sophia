"""
Installed apps on macOS: every .app bundle in /Applications, the system
apps, ~/Applications and Chrome web apps.
"""

from app.computer.application_normalizer import ApplicationNormalizer
from app.computer.macos import bundle_info, clean_name, installed_apps


class MacAppScanner:

    def __init__(self, folders=None):

        self.normalizer = ApplicationNormalizer()
        self.folders = folders

    def scan(self):

        applications = []

        for bundle in installed_apps(self.folders):

            name = clean_name(bundle.stem)
            display, _ = bundle_info(bundle)

            aliases = list(self.normalizer.aliases(name) or [])

            if display.lower() != name.lower():
                aliases.append(display.lower())

            applications.append({
                "name": name,
                "aliases": aliases,
                "app": str(bundle),
                # quitting goes through the app's name
                "process": name,
                "type": "mac",
            })

        return applications
