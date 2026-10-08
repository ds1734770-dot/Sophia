class PendingActionEngine:
    """
    Handles the user's answer to a question Sophia asked.

    "confirm": a risky tool is waiting for yes / no.
    Any other message cancels the question and is handled normally, so
    Sophia never gets stuck waiting.
    """

    YES = {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "confirm", "do it", "go ahead"}

    NO = {"no", "n", "nope", "cancel", "stop", "don't", "dont"}

    def process(self, command, context):

        pending = context.pending_actions.current()

        if pending is None or not pending.exists():

            return {
                "handled": False,
                "response": None,
            }

        if pending.action == "confirm":

            answer = command.strip().lower().rstrip(".!")

            tool = pending.data["tool"]
            args = pending.data["args"]

            context.pending_actions.clear()

            if answer in self.YES:

                result = context.registry.execute(
                    tool, args, context, confirmed=True
                )

                return {
                    "handled": True,
                    "response": result.message,
                }

            if answer in self.NO:

                return {
                    "handled": True,
                    "response": "Okay, cancelled.",
                }

            # Something else: forget the question, handle as normal
            return {
                "handled": False,
                "response": None,
            }

        context.pending_actions.clear()

        return {
            "handled": False,
            "response": None,
        }
