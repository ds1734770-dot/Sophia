from app.browser.browser_manager import BrowserManager


class BrowserEngine:

    def __init__(self):
        self.browser = BrowserManager()

    def execute(self, command, context):

        command = command.lower().strip()

        # -----------------------
        # Open websites
        # -----------------------

        if command.startswith("open "):

            website = command.replace("open ", "").strip()

            success, response = self.browser.open_website(
                website
            )

            if success:
                return {
                    "handled": True,
                    "response": response
                }

        # -----------------------
        # Google Search
        # -----------------------

        if command.startswith("search google for"):

            query = command.replace(
                "search google for",
                ""
            ).strip()

            success, response = self.browser.google_search(
                query
            )

            if success:
                return {
                    "handled": True,
                    "response": response
                }

        # -----------------------
        # YouTube Search
        # -----------------------

        if command.startswith("search youtube for"):

            query = command.replace(
                "search youtube for",
                ""
            ).strip()

            success, response = self.browser.youtube_search(
                query
            )

            if success:
                return {
                    "handled": True,
                    "response": response
                }

        return {
            "handled": False,
            "response": None
        }