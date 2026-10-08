import sys

from app.logging_setup import setup_logging
from app.sophia import Sophia


def main():

    # Emoji in the banner crash legacy Windows code pages.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    setup_logging()

    assistant = Sophia()
    assistant.start()
    assistant.chat()


if __name__ == "__main__":
    main()
