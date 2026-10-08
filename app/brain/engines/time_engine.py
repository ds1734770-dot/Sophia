import re
from datetime import datetime


class TimeEngine:
    """
    Answers direct questions about the current time or date.

    Only whole questions match, so "explain time complexity" or
    "sometimes I feel lost" go to the chat model instead.
    """

    TIME_PATTERN = re.compile(
        r"^(?:(?:hey |hi )?(?:sophia )?)?(?:please )?"
        r"(?:what(?:'s| is)? (?:the )?(?:current )?time(?: is it)?(?: now| right now)?"
        r"|what time is it(?: now| right now)?"
        r"|(?:tell me|give me|show me) the (?:current )?time"
        r"|current time|time now|time|the time)$"
    )

    DATE_PATTERN = re.compile(
        r"^(?:please )?"
        r"(?:what(?:'s| is)? (?:the )?(?:today'?s )?date(?: today)?"
        r"|what day is (?:it|today)(?: today)?"
        r"|today'?s date|date|the date|current date)$"
    )

    def execute(self, command, context, offline=False):

        text = re.sub(r"[?!.,]", "", command.lower()).strip()
        text = re.sub(r"\s+", " ", text)

        if self.TIME_PATTERN.match(text):

            return {
                "handled": True,
                "response": datetime.now().strftime("%I:%M:%S %p")
            }

        if self.DATE_PATTERN.match(text):

            return {
                "handled": True,
                "response": datetime.now().strftime("%A, %d %B %Y")
            }

        return {
            "handled": False,
            "response": None
        }
