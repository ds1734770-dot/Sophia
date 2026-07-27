from pathlib import Path

from app.computer.application_discovery.executable_selector import ExecutableSelector


class ExecutableResolver:

    def __init__(self):

        self.selector = ExecutableSelector()

    def resolve(self, display_icon, install_location):

        # --------------------------------------------------
        # 1. Try DisplayIcon
        # --------------------------------------------------

        if display_icon:

            exe = display_icon.split(",")[0].strip()

            # Only accept real executables
            if exe.lower().endswith(".exe"):

                if Path(exe).exists():

                    return exe

        # --------------------------------------------------
        # 2. Try InstallLocation
        # --------------------------------------------------

        if install_location:

            folder = Path(install_location)

            if folder.exists():

                executables = [

                    str(exe)

                    for exe in folder.rglob("*.exe")

                ]

                selected = self.selector.select(

                    folder.name,

                    executables,

                )

                if selected:

                    return selected

        # --------------------------------------------------
        # 3. Nothing Found
        # --------------------------------------------------

        return None