import re


class MemoryFilter:
    """
    Decides whether a message might contain a lasting personal fact.

    Extraction costs an AI request, so it only runs for messages that
    sound like the user talking about themselves.
    """

    PERSONAL = re.compile(
        r"\b("
        r"my (?:name|favou?rite|birthday|age|major|course|college|"
        r"university|school|job|goal|hobby|hobbies|city|country|dream|"
        r"friend|brother|sister|mother|father|mom|dad)"
        r"|i am|i'm|i was|i live|i study|i work|i like|i love|i hate|"
        r"i prefer|i enjoy|i use|i want to (?:learn|become|be)|"
        r"call me|remember (?:that|this)|from now on|actually my"
        r")\b",
        re.IGNORECASE,
    )

    @classmethod
    def should_extract(cls, text):

        text = text.strip()

        # Too short to hold a fact
        if len(text.split()) <= 2:
            return False

        # Commands and pure questions carry no facts about the user
        if text.endswith("?") and not re.search(
            r"remember|my name", text, re.IGNORECASE
        ):
            return False

        return bool(cls.PERSONAL.search(text))
