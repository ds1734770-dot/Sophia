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

            if not parsed.entity:
                return {
                    "handled": True,
                    "response": "What would you like me to open?",
                }

            success, app_response = self.computer.open_app(
                parsed.entity
            )

            if success:

                return {
                    "handled": True,
                    "response": app_response,
                }

            success, response = self.computer.open_folder(
                parsed.entity
            )

            if success:

                return {
                    "handled": True,
                    "response": response,
                }

            # Keep the "Did you mean ..." suggestions
            if "Did you mean" in app_response:

                return {
                    "handled": True,
                    "response": app_response,
                }

            # A long sentence is conversation, not an app name
            if len(parsed.entity.split()) > 3:

                return {
                    "handled": False,
                    "response": None,
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

            if not parsed.entity:
                return {
                    "handled": True,
                    "response": "What would you like me to close?",
                }

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

            if len(parsed.entity.split()) > 3:

                return {
                    "handled": False,
                    "response": None,
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