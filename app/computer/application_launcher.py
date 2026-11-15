import subprocess
import sys
from subprocess import Popen

from app.computer.application_discovery.shortcut_resolver import ShortcutResolver
from app.computer.history.launch_history_manager import LaunchHistoryManager


class ApplicationLauncher:

    def __init__(self):

        self.resolver = ShortcutResolver()
        self.history = LaunchHistoryManager()

    # ----------------------------------------

    def launch(self, application):

        # macOS app bundles
        if "app" in application:

            Popen(
                ["open", "-a", application["app"]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            self.history.increment(
                application["name"]
            )

            return True, f"Opening {application['name']}..."

        # Registry applications
        if "exe" in application:

            Popen([application["exe"]])

            self.history.increment(
                application["name"]
            )

            return True, f"Opening {application['name']}..."

        # Shortcut applications
        if "shortcut" in application:

            if sys.platform == "win32":
                import os
                os.startfile(application["shortcut"])

            else:
                from app.computer.macos import open_path
                open_path(application["shortcut"])

            self.history.increment(
                application["name"]
            )

            return True, f"Opening {application['name']}..."

        return False, "Unable to launch application."