import sys

from app.logging_setup import setup_logging


def run_cli():

    from app.sophia import Sophia

    # Emoji in replies crash legacy Windows code pages.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    setup_logging()

    assistant = Sophia()
    assistant.start()
    assistant.chat()


def main():

    if "--cli" in sys.argv:
        run_cli()
        return

    from app.ui.app import run_gui

    sys.exit(
        run_gui(
            voice="--no-voice" not in sys.argv,
            minimized="--minimized" in sys.argv,
            orb_mode="--chat" not in sys.argv,
        )
    )


if __name__ == "__main__":
    main()
