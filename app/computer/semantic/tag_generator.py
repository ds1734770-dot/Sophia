class TagGenerator:
    STOP_WORDS = {
    "for",
    "and",
    "by",
    "the",
    "of",
    "with",
    "to",
    "in",
    "on",
    "a",
    "an"
}

    DEFAULT_TAGS = {

        "chrome": [
            "browser",
            "internet",
            "web",
            "search",
            "google"
        ],

        "edge": [
            "browser",
            "internet",
            "web",
            "microsoft"
        ],

        "firefox": [
            "browser",
            "internet",
            "web"
        ],

        "visual studio code": [
            "coding",
            "programming",
            "developer",
            "editor",
            "ide",
            "code"
        ],

        "git bash": [
            "terminal",
            "shell",
            "git",
            "command",
            "bash"
        ],

        "windows terminal": [
            "terminal",
            "shell",
            "command"
        ],

        "powershell": [
            "terminal",
            "shell",
            "command"
        ],

        "spotify": [
            "music",
            "songs",
            "audio",
            "player"
        ],

        "chatgpt": [
            "ai",
            "assistant",
            "llm",
            "gpt"
        ]
    }

    # ----------------------------------------

    def generate(self, app_name):

        name = app_name.lower()

        tags = []

        for keyword, values in self.DEFAULT_TAGS.items():

            if keyword in name:

                tags.extend(values)

        # Include words from the application name
        for word in name.split():

            if word not in self.STOP_WORDS:
            
                tags.append(word)

        return sorted(set(tags))