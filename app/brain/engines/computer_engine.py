from app.brain.command_parser.command_parser import CommandParser
from app.computer.computer_manager import ComputerManager


class ComputerEngine:

    def __init__(self):

        self.computer = ComputerManager()
        self.parser = CommandParser()

    MAX_ENTITY_WORDS = 4

    @classmethod
    def _is_compound(cls, entity):

        words = entity.split()

        return (
            len(words) > cls.MAX_ENTITY_WORDS
            or any(w in ("and", "then", "also") for w in words)
        )

    # --------------------------------------------------

    def execute(self, command, context):

        parsed = self.parser.parse(command)

        # Only short, single commands are handled here. Compound or
        # long requests ("open X and then ...") are left to Gemini.
        if parsed.action in ("open", "close") and self._is_compound(parsed.entity):

            return {
                "handled": False,
                "response": None,
            }

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

            # Known app: ask the registry (it asks for confirmation).
            # Only ask when the app can actually be closed.
            if self.computer.can_close(parsed.entity):

                result = context.registry.execute(
                    "close_application",
                    {"name": parsed.entity},
                    context,
                )

                return {
                    "handled": True,
                    "response": result.message,
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