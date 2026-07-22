class BrowserPreferences:
    """
    Stores Sophia's browser preferences.
    """

    DEFAULT_BROWSER = "chrome"

    BROWSERS = {
        "chrome": {
            "path": None,  # Use system default browser
        },

        "comet": {
            "path": r"C:\Users\me\AppData\Local\Perplexity\Comet\Application\comet.exe",
        },
    }

    WEBSITE_PREFERENCES = {
        "youtube": "comet",

        "google": "chrome",
        "github": "chrome",
        "chatgpt": "chrome",
        "stackoverflow": "chrome",
    }

    @classmethod
    def browser_for(cls, website):

        return cls.WEBSITE_PREFERENCES.get(
            website,
            cls.DEFAULT_BROWSER
        )

    @classmethod
    def browser_path(cls, browser):

        return cls.BROWSERS[browser]["path"]