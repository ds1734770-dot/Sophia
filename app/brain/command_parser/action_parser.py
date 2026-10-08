import re


class ActionParser:
    """
    Decide which computer action a message asks for.

    A message is only a command when its first meaningful word is an
    action verb ("open chrome", "can you please close notepad"). Verbs
    that appear later in a sentence ("how do I run a script") are
    ordinary conversation.
    """

    OPEN_WORDS = {
        "open",
        "launch",
        "start",
        "run",
    }

    CLOSE_WORDS = {
        "close",
        "quit",
        "kill",
        "terminate",
    }

    LOCK_WORDS = {
        "lock",
    }

    SEARCH_WORDS = {
        "search",
        "google",
    }

    YOUTUBE_WORDS = {
        "youtube",
    }

    FILLER = re.compile(
        r"^(?:(?:hey|hi|hello|ok|okay)\s+)?"
        r"(?:sophia\s+)?"
        r"(?:please\s+)?"
        r"(?:(?:can|could|would|will)\s+you\s+)?"
        r"(?:please\s+)?"
        r"(?:i\s+(?:want|need)\s+you\s+to\s+)?"
        r"(?:go\s+ahead\s+and\s+)?"
    )

    # --------------------------------------

    @classmethod
    def clean(cls, text):
        """
        Lowercase, drop punctuation and leading politeness.
        """

        text = re.sub(r"[?!.,;:]", " ", text.lower())
        text = re.sub(r"\s+", " ", text).strip()

        return cls.FILLER.sub("", text).strip()

    def parse(self, text):

        words = self.clean(text).split()

        if not words:
            return None

        word = words[0]

        if word in self.OPEN_WORDS:
            return "open"

        if word in self.CLOSE_WORDS:
            return "close"

        if word in self.LOCK_WORDS:
            return "lock"

        if word in self.SEARCH_WORDS:
            return "search"

        if word in self.YOUTUBE_WORDS:
            return "youtube"

        return None
