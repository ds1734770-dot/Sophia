"""
Tell Sophia what an agent is doing. Standard library only, so a coding
agent's hook can run it quickly without Sophia's environment.

    notify.py --home DATA claude [--relay SECONDS]    (Claude Code hook; reads the hook JSON from stdin)
    notify.py --home DATA send --agent NAME --status STATUS [--title T] [--message M] [--question Q]
    notify.py --home DATA wrap --agent NAME [--title T] -- command args...

It never breaks the agent: if Sophia is not running it exits quietly.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TIMEOUT = 2.0


# ---------------------------------------------------------------
# Talking to Sophia
# ---------------------------------------------------------------

def hub_info(home):

    try:
        return json.loads((Path(home) / "agent_hub.json").read_text(encoding="utf-8"))

    except (OSError, ValueError):
        return None


def _request(home, method, path, body=None, timeout=TIMEOUT):

    info = hub_info(home)

    if not info:
        return None

    data = json.dumps(body).encode("utf-8") if body is not None else None

    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-Sophia-Token": info["token"]},
    )

    try:

        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    except (OSError, ValueError, urllib.error.URLError):
        return None


def post_event(home, event):

    return _request(home, "POST", "/event", event) is not None


def wait_answer(home, task, seconds):
    """
    The user's reply to a question, or None.
    """

    query = urllib.parse.urlencode({"task": task, "wait": seconds})

    reply = _request(home, "GET", f"/answer?{query}", timeout=seconds + 5)

    return (reply or {}).get("answer")


# ---------------------------------------------------------------
# Claude Code hooks
# ---------------------------------------------------------------

def looks_like_question(text):
    """
    Does the agent's last message end by asking the user something?
    """

    paragraphs = [p.strip() for p in (text or "").strip().split("\n\n") if p.strip()]

    return bool(paragraphs) and paragraphs[-1].rstrip("*_ `)\"'").endswith("?")


def event_from_claude_hook(payload):
    """
    Turn what a Claude Code hook receives into a report for Sophia, or
    None when the hook is not worth reporting.
    """

    name = payload.get("hook_event_name", "")

    event = {
        "agent": "Claude Code",
        "task": f"claude:{payload.get('session_id', 'session')}",
        "project": Path(payload.get("cwd") or ".").name,
    }

    if name == "UserPromptSubmit":

        event.update(status="running", title=(payload.get("prompt") or "").strip()[:100])

        return event

    if name == "Notification":

        kind = payload.get("notification_type") or ""
        message = payload.get("message") or ""

        if kind == "agent_completed":

            event.update(status="done", message=message)

            return event

        wants_you = kind in ("permission_prompt", "agent_needs_input", "elicitation_dialog") or (
            not kind and ("permission" in message.lower() or "needs" in message.lower())
        )

        if not wants_you:
            return None

        event.update(status="needs_input", message=message, question=message)

        return event

    if name == "Stop":

        last = (payload.get("last_assistant_message") or "").strip()

        if looks_like_question(last):

            question = [p for p in last.split("\n\n") if p.strip()][-1].strip()

            event.update(status="needs_input", message=last[-300:], question=question)

        else:
            event.update(status="done", message=last[:300])

        return event

    return None


def run_claude_hook(home, stdin, stdout, relay=0):

    try:
        payload = json.loads(stdin.read() or "{}")

    except ValueError:
        return 0

    event = event_from_claude_hook(payload)

    if event is None:
        return 0

    if not post_event(home, event):
        return 0

    # Stop with a question: wait for the user's reply from Sophia and, if
    # it comes, hand it to Claude so the work carries on
    if relay and payload.get("hook_event_name") == "Stop" and event["status"] == "needs_input":

        answer = wait_answer(home, event["task"], relay)

        if answer:

            post_event(home, {"agent": event["agent"], "task": event["task"],
                              "project": event["project"], "status": "running"})

            stdout.write(json.dumps({
                "decision": "block",
                "reason": f"The user replied through Sophia: {answer}",
            }))

    return 0


# ---------------------------------------------------------------
# Command line
# ---------------------------------------------------------------

def run_wrapped(home, agent, title, command):

    task = f"{agent}:{os.getpid()}"
    title = title or " ".join(command)[:100]

    post_event(home, {"agent": agent, "task": task, "status": "running", "title": title})

    try:
        code = subprocess.call(command)

    except KeyboardInterrupt:
        code = 130

    except OSError as e:

        post_event(home, {"agent": agent, "task": task, "status": "failed", "message": str(e)})

        return 127

    post_event(home, {
        "agent": agent, "task": task, "title": title,
        "status": "done" if code == 0 else "failed",
        "message": "" if code == 0 else f"Exited with code {code}",
    })

    return code


def main(argv=None, stdin=None, stdout=None):

    parser = argparse.ArgumentParser(prog="notify")

    parser.add_argument("--home", required=True)

    sub = parser.add_subparsers(dest="mode", required=True)

    claude = sub.add_parser("claude")
    claude.add_argument("--relay", type=float, default=0)

    send = sub.add_parser("send")
    send.add_argument("--agent", required=True)
    send.add_argument("--status", required=True)
    send.add_argument("--title", default="")
    send.add_argument("--message", default="")
    send.add_argument("--question", default="")
    send.add_argument("--task", default="")
    send.add_argument("--project", default="")

    wrap = sub.add_parser("wrap")
    wrap.add_argument("--agent", required=True)
    wrap.add_argument("--title", default="")
    wrap.add_argument("command", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)

    if args.mode == "claude":
        return run_claude_hook(args.home, stdin or sys.stdin, stdout or sys.stdout, args.relay)

    if args.mode == "send":

        ok = post_event(args.home, {
            "agent": args.agent, "status": args.status, "title": args.title,
            "message": args.message, "question": args.question,
            "task": args.task, "project": args.project,
        })

        return 0 if ok else 1

    command = [c for c in args.command if c != "--"] if args.command[:1] == ["--"] else args.command

    if not command:

        print("Nothing to run. Example: notify.py --home DATA wrap --agent freebuff -- freebuff", file=sys.stderr)

        return 2

    return run_wrapped(args.home, args.agent, args.title, command)


if __name__ == "__main__":

    sys.exit(main())
