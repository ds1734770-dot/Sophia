import re


class CalculatorEngine:

    def execute(self, command, context):

        command = command.strip()

        # Detect simple math expressions
        if re.fullmatch(r"[0-9+\-*/(). ]+", command):

            try:
                result = eval(command)

                return {
                    "handled": True,
                    "response": str(result)
                }

            except Exception:
                return {
                    "handled": False,
                    "response": None
                }

        return {
            "handled": False,
            "response": None
        }