import subprocess
import webbrowser
from urllib.parse import quote

from app.browser.browser_preferences import BrowserPreferences


class BrowserManager:

    WEBSITES = {
        "google": "https://www.google.com",
        "youtube": "https://www.youtube.com",
        "github": "https://github.com",
        "chatgpt": "https://chat.openai.com",
        "stackoverflow": "https://stackoverflow.com",
    }

    def _open_url(self, url, website):
        """
        Opens a URL using the preferred browser for the website.
        """

        browser = BrowserPreferences.browser_for(website)
        browser_path = BrowserPreferences.browser_path(browser)

        try:

            if browser_path is None:
                webbrowser.open(url)

            else:
                subprocess.Popen([
                    browser_path,
                    url,
                ])

            return True, f"Opening {website.title()}..."

        except Exception as e:
            return False, str(e)

    def open_url(self, url):
        """
        Open any http(s) URL in the default browser.
        """

        if not url.lower().startswith(("http://", "https://")):
            return False, "Only http and https links can be opened."

        try:
            webbrowser.open(url)
            return True, f"Opening {url}..."

        except Exception as e:
            return False, str(e)

    def open_website(self, website):
        """
        Open a website.
        """

        website = website.lower().strip()

        if website not in self.WEBSITES:
            return False, f"I don't know the website '{website}'."

        return self._open_url(
            self.WEBSITES[website],
            website
        )

    def google_search(self, query):
        """
        Search Google.
        """

        url = (
            "https://www.google.com/search?q="
            f"{quote(query)}"
        )

        try:
            success, _ = self._open_url(
                url,
                "google"
            )

            if success:
                return True, f"Searching Google for '{query}'."

            return False, "Failed to open Google."

        except Exception as e:
            return False, str(e)

    def youtube_search(self, query):
        """
        Search YouTube.
        """

        url = (
            "https://www.youtube.com/results?"
            f"search_query={quote(query)}"
        )

        try:
            success, _ = self._open_url(
                url,
                "youtube"
            )

            if success:
                return True, f"Searching YouTube for '{query}'."

            return False, "Failed to open YouTube."

        except Exception as e:
            return False, str(e)