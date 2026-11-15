"""
First-run setup, in the terminal:  python main.py --setup

1. Gemini API key (stored in the Keychain / Windows Credential Manager)
2. Scan the installed apps, so "open chrome" works at once
3. Permissions: microphone, accessibility, screen recording, automation
   (macOS asks once per app; this triggers each prompt and checks it)
4. Download the voice models, so the first voice request is quick
5. Optionally start Sophia at login

Every step can be run again safely. --yes accepts the defaults (for
scripts); --skip-models leaves the voice download for the first use.
"""

import getpass
import subprocess
import sys
import time

IS_MAC = sys.platform == "darwin"

GREEN, YELLOW, RED, DIM, BOLD, RESET = (
    ("\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m")
    if sys.stdout.isatty() else ("",) * 6
)

MAC_SETTINGS = {
    "microphone": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "screen": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    "automation": "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
}


def heading(number, text):

    print(f"\n{BOLD}[{number}] {text}{RESET}")


def ok(text):

    print(f"    {GREEN}✓{RESET} {text}")


def warn(text):

    print(f"    {YELLOW}!{RESET} {text}")


def fail(text):

    print(f"    {RED}✗{RESET} {text}")


def ask(question, default=True, assume_yes=False):

    if assume_yes or not sys.stdin.isatty():
        return default

    hint = "Y/n" if default else "y/N"

    answer = input(f"    {question} [{hint}] ").strip().lower()

    if not answer:
        return default

    return answer.startswith("y")


def terminal_app():
    """
    The app macOS gives permissions to: the one this terminal runs in.
    """

    import os

    program = os.getenv("TERM_PROGRAM", "")

    return {
        "Apple_Terminal": "Terminal",
        "iTerm.app": "iTerm",
        "vscode": "Visual Studio Code",
        "WarpTerminal": "Warp",
    }.get(program, program or "your terminal app")


# ---------------------------------------------------------------
# Steps
# ---------------------------------------------------------------

def step_api_key(assume_yes):

    import os

    from app.config.secrets import get_stored_api_key, store_api_key

    heading(1, "Gemini API key")

    if os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_KEY") != "your-key-here":
        ok("Found GEMINI_API_KEY in the environment / .env")
        return True

    if get_stored_api_key():
        ok("A key is already saved on this computer")
        return True

    if assume_yes or not sys.stdin.isatty():
        warn("No key yet. Sophia asks for one when it starts.")
        return False

    print(f"    Get a free key at {BOLD}https://aistudio.google.com/apikey{RESET}")

    key = getpass.getpass("    Paste it here (hidden, Enter to skip): ").strip()

    if not key:
        warn("Skipped. Sophia asks for the key when it starts.")
        return False

    if store_api_key(key):
        ok("Saved in the " + ("Keychain" if IS_MAC else "Windows Credential Manager"))
        return True

    fail("Could not save the key; put GEMINI_API_KEY=... in a .env file instead")
    return False


def step_apps():

    heading(2, "Scanning installed apps")

    from app.computer.application_manager import ApplicationManager

    started = time.monotonic()

    manager = ApplicationManager()
    manager.refresh()

    apps = manager.indexer.load()

    names = sorted(a["name"] for a in apps)

    ok(f"Found {len(apps)} apps in {time.monotonic() - started:.1f} s")

    if names:
        print(f"    {DIM}" + ", ".join(names[:12]) + (" ..." if len(names) > 12 else "") + RESET)

    for query in ("chrome", "notepad", "terminal", "settings"):

        found = manager.find(query)

        if found:
            print(f"    {DIM}\"open {query}\" -> {found['name']}{RESET}")

    return len(apps) > 0


def check_microphone():
    """
    Record half a second. Denied access records pure silence.
    """

    try:

        import numpy as np
        import sounddevice as sd

        audio = sd.rec(int(0.6 * 16000), samplerate=16000, channels=1, dtype="float32")
        sd.wait()

        return bool(np.abs(audio).max() > 0)

    except Exception:
        return False


def step_permissions(assume_yes):

    heading(3, "Permissions (voice, screen and control)")

    results = {}

    # Microphone: the first recording makes macOS / Windows ask
    print("    Checking the microphone (say something)...")

    results["Microphone"] = check_microphone()

    if results["Microphone"]:
        ok("Microphone works")

    else:

        fail("No sound from the microphone")

        if IS_MAC:
            warn(f"Allow {terminal_app()} under Privacy & Security > Microphone")
            subprocess.run(["open", MAC_SETTINGS["microphone"]], check=False)

        else:
            warn("Settings > Privacy & security > Microphone: allow desktop apps")

    if not IS_MAC:

        ok("Screen control and screenshots need no extra permission on Windows")

        return results

    # Accessibility: reading buttons, clicking, typing, window control
    try:

        import ApplicationServices as ax

        trusted = ax.AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True})

    except Exception:
        trusted = False

    results["Accessibility"] = bool(trusted)

    if trusted:
        ok("Accessibility (click, type, control windows)")

    else:
        fail("Accessibility not allowed yet")
        warn(f"Switch on {terminal_app()} under Privacy & Security > Accessibility")
        subprocess.run(["open", MAC_SETTINGS["accessibility"]], check=False)

    # Screen Recording: screenshots, "what is on my screen", window titles
    try:

        import Quartz

        allowed = Quartz.CGPreflightScreenCaptureAccess() or Quartz.CGRequestScreenCaptureAccess()

    except Exception:
        allowed = False

    results["Screen Recording"] = bool(allowed)

    if allowed:
        ok("Screen Recording (screenshots, reading the screen)")

    else:
        fail("Screen Recording not allowed yet")
        warn(f"Switch on {terminal_app()} under Privacy & Security > Screen & System Audio Recording")
        subprocess.run(["open", MAC_SETTINGS["screen"]], check=False)

    # Automation: volume, dark mode, Finder windows go through System Events
    from app.computer.macos import osascript

    automation, error = osascript('tell application "System Events" to get name of first process')

    results["Automation"] = automation

    if automation:
        ok("Automation (volume, dark mode, Finder)")

    else:
        fail("Automation of System Events not allowed yet")
        warn(f"Allow {terminal_app()} to control System Events under Privacy & Security > Automation")

    if not all(results.values()):
        warn("macOS applies new permissions after Sophia restarts. Run this setup again to check.")

    return results


def step_models(assume_yes, skip):

    heading(4, "Voice models (about 500 MB, downloaded once)")

    if skip or not ask("Download them now, so voice is ready at once?", True, assume_yes):
        warn("Skipped: they download the first time you use voice")
        return False

    from app.config.settings import Settings
    from app.settings.paths import DATA_DIR

    settings = Settings()

    loaders = []

    try:

        from app.voice.moonshine import MoonshineTranscriber

        loaders.append(("speech recognition (Moonshine)", MoonshineTranscriber(settings.moonshine_model).preload))
        loaders.append(("wake word check", MoonshineTranscriber("tiny").preload))

    except Exception:
        pass

    from app.voice.listener import Transcriber

    loaders.append(("speech recognition fallback (Whisper)", Transcriber(settings.whisper_model).preload))

    from app.voice.piper_voice import PiperEngine

    piper = PiperEngine(settings.piper_voice, DATA_DIR / "models" / "piper")

    loaders.append((f"voice ({settings.piper_voice})", piper.preload))

    try:

        from openwakeword.utils import download_models

        loaders.append(("wake word (Hey Jarvis)", download_models))

    except Exception:
        pass

    done = True

    for label, load in loaders:

        print(f"    {DIM}Loading {label}...{RESET}")

        try:
            load()
            ok(label)

        except Exception as e:
            fail(f"{label}: {e}")
            done = False

    return done


def step_autostart(assume_yes):

    heading(5, "Start at login")

    from app.computer.autostart import default_autostart

    autostart = default_autostart()

    if autostart.is_enabled():
        ok("Already starts at login")
        return True

    if ask("Start Sophia automatically when you log in?", False, assume_yes):
        autostart.enable()
        ok("Sophia will start at login")
        return True

    print(f"    {DIM}Not now (change it later from the chat menu){RESET}")

    return False


def run(argv=None):

    argv = sys.argv[1:] if argv is None else argv

    assume_yes = "--yes" in argv or "-y" in argv
    skip_models = "--skip-models" in argv

    from dotenv import load_dotenv

    load_dotenv()

    print(f"\n{BOLD}Sophia setup{RESET}  {DIM}({'macOS' if IS_MAC else sys.platform}){RESET}")

    step_api_key(assume_yes)
    step_apps()
    permissions = step_permissions(assume_yes)
    step_models(assume_yes, skip_models)
    step_autostart(assume_yes)

    print(f"\n{BOLD}All set.{RESET} Start Sophia with:")

    if IS_MAC:
        print("    sophia            (or double-click Sophia.command)")

    else:
        print("    sophia            (or: python main.py)")

    print(f"{DIM}Try: \"open YouTube\", \"open Chrome\", \"what's the weather\", or say \"Hey Jarvis\".{RESET}")

    missing = [name for name, allowed in permissions.items() if not allowed]

    if missing:
        print(f"{YELLOW}Still to allow: {', '.join(missing)} (then run: sophia --setup){RESET}")

    return 0
