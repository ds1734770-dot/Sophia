class PendingActionEngine:

    def process(self, command, context):

        pending = context.pending_actions.current()

        if pending is None or not pending.exists():

            return {
                "handled": False,
                "response": None,
            }

        # ----------------------------
        # Rename
        # ----------------------------

        if pending.action == "rename":

            try:

                choice = int(command.strip()) - 1

            except ValueError:

                return {
                    "handled": True,
                    "response": "Please enter a valid number.",
                }

            if choice < 0 or choice >= len(pending.matches):

                return {
                    "handled": True,
                    "response": "Invalid selection.",
                }

            selected = pending.matches[choice]

            new_name = pending.data["new_name"]

            success, response = context.file_manager.rename(
                selected["path"],
                new_name,
            )

            if success:

                context.file_indexer.save()

                context.pending_actions.clear()

            return {
                "handled": True,
                "response": response,
            }

        return {
            "handled": False,
            "response": None,
        }