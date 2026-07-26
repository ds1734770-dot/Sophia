



from app.computer.computer_manager import ComputerManager



class ComputerEngine:

    def __init__(self):
        self.computer = ComputerManager()

    def execute(self, command,context):

        command = command.lower().strip()

        # ----------------------------
        # Open Applications / Folders
        # ----------------------------

        if command.startswith("open "):

            target = command.replace("open ", "").strip()

            success, response = self.computer.open_app(target)

            if success:
                return {
                    "handled": True,
                    "response": response,
                }

            success, response = self.computer.open_folder(target)

            if success:
                return {
                    "handled": True,
                    "response": response,
                }

            return {
                "handled": True,
                "response": f"I couldn't find an application or folder named '{target}'."
}

        # ----------------------------
        # Close Applications
        # ----------------------------

        if command.startswith("close "):

            target = command.replace("close ", "").strip()

            success, response = self.computer.close_app(target)

            if success:
                return {
                    "handled": True,
                    "response": response,
                }

            success, response = self.computer.close_folder(target)

            if success:
                return {
                    "handled": True,
                    "response": response,
                }

            return {
                "handled": True,
                "response": f"I couldn't find an application or folder named '{target}' to close."
                }

        # ----------------------------
        # Lock Computer
        # ----------------------------

        if command in [
            "lock",
            "lock pc",
            "lock computer",
            "lock the computer",
            "lock screen",
            "lock the screen",
        ]:

            success, response = self.computer.lock()

            return {
                "handled": success,
                "response": response,
            }

        return {
            "handled": False,
            "response": None,
        }