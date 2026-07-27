from subprocess import Popen
from app.computer.application_discovery.shortcut_resolver import ShortcutResolver
import shlex


class ApplicationLauncher:

    def __init__(self):

        self.resolver = ShortcutResolver()

    def launch(self, application):

        # Registry applications
        if "exe" in application:

            Popen([application["exe"]])

            return True, f"Opening {application['name']}..."

        # Shortcut-based applications
        if "shortcut" in application:

            info = self.resolver.resolve(application["shortcut"])

            if info is None:
                return False, "Unable to resolve shortcut."

            command = [info["target"]]

            if info["arguments"]:

                command.extend(shlex.split(info["arguments"], posix=False))

            Popen(
                command,
                cwd=info["working_directory"] or None,
            )

            return True, f"Opening {application['name']}..."

        return False, "Unable to launch application."