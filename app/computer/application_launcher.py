import os
from subprocess import Popen

from app.computer.application_discovery.shortcut_resolver import ShortcutResolver
from app.computer.history.launch_history_manager import LaunchHistoryManager


class ApplicationLauncher:

    def __init__(self):

        self.resolver = ShortcutResolver()
        self.history = LaunchHistoryManager()

    # ----------------------------------------

    def launch(self, application):

        # Registry applications
        if "exe" in application:

            Popen([application["exe"]])

            self.history.increment(
                application["name"]
            )

            return True, f"Opening {application['name']}..."

        # Shortcut applications
        if "shortcut" in application:

            os.startfile(
                application["shortcut"]
            )

            self.history.increment(
                application["name"]
            )

            return True, f"Opening {application['name']}..."

        return False, "Unable to launch application."