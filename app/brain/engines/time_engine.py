from datetime import datetime


class TimeEngine:

    def execute(self, command):

        command = command.lower()

        keywords = [
            "time",
            "what time",
            "current time",
            "tell me the time"
        ]

        if any(word in command for word in keywords):

            return {
                "handled": True,
                "response": datetime.now().strftime("%I:%M:%S %p")
            }

        return {
            "handled": False,
            "response": None
        }