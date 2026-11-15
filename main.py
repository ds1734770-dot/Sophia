"""
Sophia, a personal AI assistant for macOS and Windows.

Usage:
  sophia                 the floating car (hover for Voice / Chat / Hide)
  sophia --chat          the chat window instead of the car
  sophia --cli           text-only, in the terminal
  sophia --no-voice      no microphone or spoken replies
  sophia --minimized     start hidden (used when starting at login)
  sophia --setup         first-run setup: API key, app scan, permissions,
                         voice models (add --yes to accept the defaults,
                         --skip-models to download them later)
  sophia --trust-plugin FILE    allow a plugin from your plugins folder
  sophia --untrust-plugin FILE  stop loading it
"""

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

    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__.strip())
        return

    if "--trust-plugin" in sys.argv or "--untrust-plugin" in sys.argv:

        from app.settings.paths import DATA_DIR
        from app.tools.plugins import TRUST_FILE, PluginTrust, trust_plugin_command

        sys.exit(trust_plugin_command(sys.argv, DATA_DIR / "plugins", PluginTrust(DATA_DIR / TRUST_FILE)))

    if "--setup" in sys.argv:
        from app.setup_wizard import run
        sys.exit(run())

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
