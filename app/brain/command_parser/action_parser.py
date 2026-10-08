class ActionParser:

    OPEN_WORDS = {
        "open",
        "launch",
        "start",
        "run",
    }

    CLOSE_WORDS = {
        "close",
        "quit",
        "exit",
        "stop",
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

    # --------------------------------------

    def parse(self, text):

        words = text.lower().split()

        for word in words:

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