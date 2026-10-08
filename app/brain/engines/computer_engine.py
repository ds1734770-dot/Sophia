from app.brain.command_parser.command_parser import CommandParser
from app.computer.computer_manager import ComputerManager


class ComputerEngine:

    def __init__(self):

        self.computer = ComputerManager()
        self.parser = CommandParser()

    # --------------------------------------------------

    def execute(self, command, context):

        parsed = self.parser.parse(command)

        # --------------------------------------------------
        # OPEN
        # --------------------------------------------------

        if parsed.action == "open":

            success, response = self.computer.open_app(
                parsed.entity
            )

            if success:

                return {
                    "handled": True,
                    "response": response,
                }

            success, response = self.computer.open_folder(
                parsed.entity
            )

            if success:

                return {
                    "handled": True,
                    "response": response,
                }

            return {
                "handled": True,
                "response": (
                    f"I couldn't find an application or folder "
                    f"named '{parsed.entity}'."
                ),
            }

        # --------------------------------------------------
        # CLOSE
        # --------------------------------------------------

        if parsed.action == "close":

            success, response = self.computer.close_app(
                parsed.entity
            )

            if success:

                return {
                    "handled": True,
                    "response": response,
                }

            success, response = self.computer.close_folder(
                parsed.entity
            )

            if success:

                return {
                    "handled": True,
                    "response": response,
                }

            return {
                "handled": True,
                "response": (
                    f"I couldn't find an application or folder "
                    f"named '{parsed.entity}' to close."
                ),
            }

        # --------------------------------------------------
        # LOCK
        # --------------------------------------------------

        if parsed.action == "lock":

            success, response = self.computer.lock()

            return {
                "handled": success,
                "response": response,
            }

        # --------------------------------------------------

        return {
            "handled": False,
            "response": None,
        }