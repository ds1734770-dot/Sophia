"""
Which browser opens which website.

Everything opens in the default browser unless SITE_BROWSERS says
otherwise, for example in .env:

    SITE_BROWSERS=youtube:comet,github:chrome

A browser that is not installed falls back to the default one.
"""

import os
import sys
from pathlib import Path

DEFAULT = "default"


def _windows_paths(*relative):

    roots = [
        os.getenv("LOCALAPPDATA"),
        os.getenv("ProgramFiles"),
        os.getenv("ProgramFiles(x86)"),
    ]

    return [str(Path(root) / r) for root in roots if root for r in relative]


# name -> (macOS app, candidate Windows programs)
BROWSERS = {
    "chrome": (
        "/Applications/Google Chrome.app",
        _windows_paths(r"Google\Chrome\Application\chrome.exe"),
    ),
    "comet": (
        "/Applications/Comet.app",
        _windows_paths(r"Perplexity\Comet\Application\comet.exe"),
    ),
    "edge": (
        "/Applications/Microsoft Edge.app",
        _windows_paths(r"Microsoft\Edge\Application\msedge.exe"),
    ),
    "brave": (
        "/Applications/Brave Browser.app",
        _windows_paths(r"BraveSoftware\Brave-Browser\Application\brave.exe"),
    ),
    "firefox": (
        "/Applications/Firefox.app",
        _windows_paths(r"Mozilla Firefox\firefox.exe"),
    ),
    "arc": ("/Applications/Arc.app", []),
    "safari": ("/Applications/Safari.app", []),
}


def parse_site_browsers(text):
    """
    "youtube:comet, github:chrome" -> {"youtube": "comet", "github": "chrome"}
    """

    preferences = {}

    for part in (text or "").split(","):

        if ":" not in part:
            continue

        site, browser = (p.strip().lower() for p in part.split(":", 1))

        if site and browser:
            preferences[site] = browser

    return preferences


class BrowserPreferences:

    @classmethod
    def preferences(cls):

        return parse_site_browsers(os.getenv("SITE_BROWSERS", ""))

    @classmethod
    def browser_for(cls, website):

        return cls.preferences().get(website, DEFAULT)

    @classmethod
    def browser_path(cls, browser):
        """
        The installed browser's app or program, or None for the default
        browser (also when the chosen one is not installed).
        """

        if browser not in BROWSERS:
            return None

        mac_app, windows_programs = BROWSERS[browser]

        candidates = [mac_app] if sys.platform == "darwin" else windows_programs

        for path in candidates:

            if path and os.path.exists(path):
                return path

        return None
