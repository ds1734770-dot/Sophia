"""
Connect agents to Sophia.

    python -m app.agents.setup            show how to connect each agent
    python -m app.agents.setup claude     show the Claude Code hooks
    python -m app.agents.setup claude --apply     add them to ~/.claude/settings.json (a backup is kept)
    python -m app.agents.setup claude --remove    take them out again

Nothing is changed unless you pass --apply or --remove.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

MARKER = "agents/notify.py"
EVENTS = ("UserPromptSubmit", "Notification", "Stop")


def _posix(path):

    return Path(path).as_posix()


def notify_script():

    return Path(__file__).with_name("notify.py")


def hook_command(python, script, home, relay=0):

    command = f'"{_posix(python)}" "{_posix(script)}" --home "{_posix(home)}" claude'

    if relay:
        command += f" --relay {int(relay)}"

    return command


def hook_entries(python, script, home, relay=0):
    """
    The hooks Claude Code needs, in its settings.json format. With relay,
    the Stop hook waits that many seconds for a reply typed into Sophia
    and passes it on to Claude.
    """

    entries = {}

    for event in EVENTS:

        use_relay = relay if event == "Stop" else 0

        entries[event] = [{
            "hooks": [{
                "type": "command",
                "command": hook_command(python, script, home, use_relay),
                "timeout": (int(use_relay) + 15) if use_relay else 10,
            }]
        }]

    return entries


def is_ours(group):

    return any(MARKER in h.get("command", "") for h in group.get("hooks", []))


def remove_ours(settings):

    hooks = settings.get("hooks", {})

    for event in list(hooks):

        hooks[event] = [g for g in hooks[event] if not is_ours(g)]

        if not hooks[event]:
            del hooks[event]

    if not hooks:
        settings.pop("hooks", None)

    return settings


def merge(settings, entries):
    """
    Add our hooks, replacing an earlier copy of them and leaving every
    other hook alone.
    """

    remove_ours(settings)

    hooks = settings.setdefault("hooks", {})

    for event, groups in entries.items():
        hooks.setdefault(event, []).extend(groups)

    return settings


def claude_settings_path():

    return Path.home() / ".claude" / "settings.json"


def apply(path, entries=None, remove=False):
    """
    Write the settings file (with a .bak copy of what was there).
    """

    path = Path(path)

    settings = {}

    if path.exists():

        try:
            settings = json.loads(path.read_text(encoding="utf-8") or "{}")

        except ValueError as e:
            raise ValueError(f"{path} is not valid JSON ({e}); not touching it") from e

        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))

    if remove:
        remove_ours(settings)

    else:
        merge(settings, entries)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    return path


def instructions(home, python=None):

    python = python or sys.executable
    script = notify_script()

    base = f'"{_posix(python)}" "{_posix(script)}" --home "{_posix(home)}"'

    return f"""Connect your agents to Sophia

Claude Code (terminal and desktop app), automatic:
    python -m app.agents.setup claude --apply
  (adds three hooks to ~/.claude/settings.json; add --relay 120 to also let you
  answer Claude's questions from Sophia)

Any terminal agent (Freebuff, Gemini CLI, Codex, ...): run it through the wrapper
    {base} wrap --agent freebuff -- freebuff
  or report by hand from any script:
    {base} send --agent gemini --status done --title "Refactor finished"

Statuses: running, needs_input, done, failed.

Chat websites and apps (claude.ai, ChatGPT, Gemini): coming with the browser extension.
"""


def main(argv=None):

    from app.settings.paths import DATA_DIR

    parser = argparse.ArgumentParser(prog="setup")
    parser.add_argument("agent", nargs="?")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--relay", type=float, default=0)
    parser.add_argument("--settings", help="settings file (default ~/.claude/settings.json)")

    args = parser.parse_args(argv)

    if args.agent != "claude":

        print(instructions(DATA_DIR))

        return 0

    path = Path(args.settings) if args.settings else claude_settings_path()

    entries = hook_entries(sys.executable, notify_script(), DATA_DIR, args.relay)

    if args.apply or args.remove:

        apply(path, entries, remove=args.remove)

        print(("Removed Sophia's hooks from " if args.remove else "Added Sophia's hooks to ") + str(path))
        print("A copy of the previous file was saved next to it (.bak). Restart Claude Code to load the hooks.")

        return 0

    print(json.dumps({"hooks": entries}, indent=2))
    print(f"\nThis is what --apply would add to {path}.")

    return 0


if __name__ == "__main__":

    sys.exit(main())
