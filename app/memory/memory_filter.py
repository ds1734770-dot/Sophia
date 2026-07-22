class MemoryFilter:

    IGNORE_PREFIXES = [

        "open",
        "close",
        "lock",
        "shutdown",
        "restart",

        "search",

        "calculate",

        "what is",
        "what's",

        "time",
        "date",

        "who is",

        "tell me",

        "explain",

        "summarize",

        "read",

    ]

    @classmethod
    def should_extract(cls, text):

        text = text.lower().strip()

        # Ignore short messages
        if len(text.split()) <= 2:
            return False

        # Ignore commands
        for prefix in cls.IGNORE_PREFIXES:

            if text.startswith(prefix):
                return False

        return True