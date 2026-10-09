import io
import json
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from app.agents import notify, setup
from app.agents.hub import AgentHub, normalize_agent, normalize_status
from app.agents.server import AgentServer


# ---------------------------------------------------------------
# Hub
# ---------------------------------------------------------------

def test_agent_names_get_a_family_and_a_colour():

    assert normalize_agent("Claude Code")[0] == "claude"
    assert normalize_agent("Claude Code")[1] == "Claude Code"
    assert normalize_agent("claude")[2] == "#d97757"
    assert normalize_agent("codex")[0] == "chatgpt"
    assert normalize_agent("Gemini CLI")[0] == "gemini"
    assert normalize_agent("freebuff")[2] == "#b45cff"

    # an unknown agent keeps its own name and a stable colour
    first = normalize_agent("My Tool")

    assert first[1] == "My Tool" and first == normalize_agent("My Tool")


def test_status_words():

    assert normalize_status("Finished") == "done"
    assert normalize_status("needs info") == "needs_input"
    assert normalize_status("error") == "failed"
    assert normalize_status("nonsense") is None


def test_a_task_moves_through_its_states():

    hub = AgentHub()
    seen = []
    hub.listeners.append(lambda kind, task, prev: seen.append((kind, task.status, prev)))

    hub.update({"agent": "claude", "status": "running", "title": "Fix login", "task": "t1"})
    hub.update({"agent": "claude", "status": "needs_input", "question": "Which database?", "task": "t1"})
    hub.update({"agent": "claude", "status": "done", "task": "t1"})

    task = hub.tasks["t1"]

    assert task.title == "Fix login" and task.status == "done" and task.question == ""
    assert seen == [
        ("started", "running", None),
        ("updated", "needs_input", "running"),
        ("updated", "done", "needs_input"),
    ]


def test_a_new_run_after_finishing_starts_a_fresh_task():

    hub = AgentHub()

    hub.update({"agent": "gemini", "status": "done", "task": "g"})

    first = hub.tasks["g"].started

    time.sleep(0.01)

    hub.update({"agent": "gemini", "status": "running", "task": "g"})

    assert hub.tasks["g"].started > first and hub.tasks["g"].status == "running"


def test_invalid_reports_are_ignored():

    hub = AgentHub()

    assert hub.update("nope") is None
    assert hub.update({"agent": "x", "status": "banana"}) is None
    assert hub.tasks == {}


def test_text_is_cleaned_and_limited():

    hub = AgentHub()

    task = hub.update({"agent": "a" * 500, "status": "running", "title": "x\n\n  y" + "z" * 900})

    assert "\n" not in task.title and len(task.title) <= 121
    assert len(task.label) <= 41


def test_the_car_follows_whoever_needs_you_first():

    hub = AgentHub()

    assert hub.lead() is None

    hub.update({"agent": "chatgpt", "status": "running", "task": "a"})

    time.sleep(0.01)

    hub.update({"agent": "claude", "status": "running", "task": "b"})

    assert hub.lead().agent == "claude"

    hub.update({"agent": "gemini", "status": "needs_input", "task": "c", "question": "?"})

    assert hub.lead().agent == "gemini"


def test_answers_reach_a_waiting_agent():

    hub = AgentHub()

    hub.update({"agent": "claude", "status": "needs_input", "task": "t", "question": "Sure?"})

    got = []

    waiter = threading.Thread(target=lambda: got.append(hub.wait_answer("t", 5)))
    waiter.start()

    time.sleep(0.1)

    assert hub.answer("t", "yes, go ahead")

    waiter.join(2)

    assert got == ["yes, go ahead"]
    assert hub.wait_answer("t", 0.05) is None        # delivered once
    assert not hub.answer("missing", "x")


def test_summary_reads_naturally():

    hub = AgentHub()

    assert "No agents" in hub.summary()

    hub.update({"agent": "claude", "status": "needs_input", "title": "the migration", "question": "Drop the old table?"})
    hub.update({"agent": "gemini", "status": "done", "title": "the report", "task": "g"})

    text = hub.summary()

    assert "waiting for you on the migration: Drop the old table?" in text
    assert "Gemini is finished the report" in text


# ---------------------------------------------------------------
# Server (real HTTP on this machine)
# ---------------------------------------------------------------

@pytest.fixture
def server(tmp_path):

    hub = AgentHub()
    srv = AgentServer(hub, tmp_path, port=48100)
    srv.start()

    yield srv

    srv.stop()


def call(server, method, path, body=None, token=True, origin=None):

    headers = {"Content-Type": "application/json"}

    if token:
        headers["X-Sophia-Token"] = server.token

    if origin:
        headers["Origin"] = origin

    request = urllib.request.Request(
        f"http://127.0.0.1:{server.port}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers=headers,
    )

    try:

        with urllib.request.urlopen(request, timeout=5) as r:
            return r.status, json.loads(r.read())

    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_server_accepts_reports_with_the_token(server):

    code, body = call(server, "POST", "/event", {"agent": "claude", "status": "running", "title": "x", "task": "s1"})

    assert code == 200 and body["task"] == "s1"
    assert server.hub.tasks["s1"].title == "x"


def test_server_refuses_without_or_with_a_wrong_token(server):

    assert call(server, "POST", "/event", {"agent": "a", "status": "done"}, token=False)[0] == 401

    wrong = urllib.request.Request(
        f"http://127.0.0.1:{server.port}/event", data=b"{}", method="POST",
        headers={"X-Sophia-Token": "nope"},
    )

    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(wrong, timeout=5)

    assert e.value.code == 401
    assert server.hub.tasks == {}


def test_a_web_page_cannot_report_even_with_the_token(server):

    code, _ = call(server, "POST", "/event", {"agent": "a", "status": "done"}, origin="https://evil.example")

    assert code == 401 and server.hub.tasks == {}

    # a browser extension may
    code, _ = call(server, "POST", "/event", {"agent": "a", "status": "done"}, origin="chrome-extension://abc")

    assert code == 200


def test_server_rejects_bad_input(server):

    assert call(server, "POST", "/event", {"agent": "a", "status": "banana"})[0] == 400
    assert call(server, "POST", "/nope", {})[0] == 404
    assert call(server, "GET", "/health", token=False)[0] == 200


def test_token_and_port_are_saved_for_the_notify_command(server, tmp_path):

    info = json.loads((tmp_path / "agent_hub.json").read_text())

    assert info == {"port": server.port, "token": server.token}

    again = AgentServer(AgentHub(), tmp_path, port=48120)

    assert again.token == server.token           # stays the same across restarts


def test_answer_long_poll_over_http(server):

    server.hub.update({"agent": "claude", "status": "needs_input", "task": "q", "question": "?"})

    threading.Timer(0.2, lambda: server.hub.answer("q", "use postgres")).start()

    code, body = call(server, "GET", "/answer?task=q&wait=5")

    assert code == 200 and body["answer"] == "use postgres"


# ---------------------------------------------------------------
# Claude Code hooks and the notify command
# ---------------------------------------------------------------

def hook(name, **extra):

    return {"hook_event_name": name, "session_id": "abc", "cwd": "C:/work/shop", **extra}


def test_hook_events_map_to_reports():

    start = notify.event_from_claude_hook(hook("UserPromptSubmit", prompt="fix the checkout bug"))

    assert start["status"] == "running" and start["title"] == "fix the checkout bug"
    assert start["project"] == "shop" and start["task"] == "claude:abc"

    done = notify.event_from_claude_hook(hook("Stop", last_assistant_message="All fixed and tests pass."))

    assert done["status"] == "done"

    asks = notify.event_from_claude_hook(
        hook("Stop", last_assistant_message="I changed it.\n\nShould I also update the docs?")
    )

    assert asks["status"] == "needs_input" and asks["question"] == "Should I also update the docs?"

    perm = notify.event_from_claude_hook(
        hook("Notification", notification_type="permission_prompt", message="Claude needs your permission to run Bash")
    )

    assert perm["status"] == "needs_input" and "permission" in perm["question"]

    assert notify.event_from_claude_hook(hook("Notification", notification_type="idle_prompt", message="waiting")) is None
    assert notify.event_from_claude_hook(hook("SessionEnd")) is None


def test_hook_runner_posts_to_a_running_sophia(server, tmp_path):

    stdin = io.StringIO(json.dumps(hook("UserPromptSubmit", prompt="build it")))

    assert notify.run_claude_hook(tmp_path, stdin, io.StringIO()) == 0
    assert server.hub.tasks["claude:abc"].title == "build it"


def test_hook_runner_is_silent_when_sophia_is_not_running(tmp_path):

    out = io.StringIO()
    stdin = io.StringIO(json.dumps(hook("Stop", last_assistant_message="done")))

    assert notify.run_claude_hook(tmp_path, stdin, out) == 0
    assert out.getvalue() == ""


def test_relay_hands_the_users_reply_back_to_claude(server, tmp_path):

    threading.Timer(0.3, lambda: server.hub.answer("claude:abc", "yes, update them")).start()

    out = io.StringIO()
    stdin = io.StringIO(json.dumps(hook("Stop", last_assistant_message="Done.\n\nUpdate the docs too?")))

    notify.run_claude_hook(tmp_path, stdin, out, relay=5)

    decision = json.loads(out.getvalue())

    assert decision["decision"] == "block" and "yes, update them" in decision["reason"]
    assert server.hub.tasks["claude:abc"].status == "running"


def test_relay_gives_up_quietly_when_nobody_answers(server, tmp_path):

    out = io.StringIO()
    stdin = io.StringIO(json.dumps(hook("Stop", last_assistant_message="Which one?")))

    started = time.time()

    notify.run_claude_hook(tmp_path, stdin, out, relay=0.3)

    assert out.getvalue() == "" and time.time() - started < 3


def test_send_and_wrap_commands(server, tmp_path):

    assert notify.main(
        ["--home", str(tmp_path), "send", "--agent", "gemini", "--status", "done", "--title", "Report", "--task", "g1"]
    ) == 0
    assert server.hub.tasks["g1"].status == "done"

    code = notify.main(
        ["--home", str(tmp_path), "wrap", "--agent", "freebuff", "--", sys.executable, "-c", "raise SystemExit(3)"]
    )

    wrapped = [t for t in server.hub.tasks.values() if t.agent == "freebuff"][0]

    assert code == 3 and wrapped.status == "failed" and "code 3" in wrapped.message


# ---------------------------------------------------------------
# Setup (never touches the real settings in tests)
# ---------------------------------------------------------------

def test_setup_adds_only_our_hooks_and_keeps_a_backup(tmp_path):

    path = tmp_path / "settings.json"

    path.write_text(json.dumps({
        "theme": "dark",
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]},
    }))

    entries = setup.hook_entries("C:/py/python.exe", setup.notify_script(), tmp_path / "data", relay=60)

    setup.apply(path, entries)
    setup.apply(path, entries)                       # twice: no duplicates

    settings = json.loads(path.read_text())

    assert settings["theme"] == "dark"
    assert sum(1 for g in settings["hooks"]["Stop"] if setup.is_ours(g)) == 1
    assert any("echo mine" in h["command"] for g in settings["hooks"]["Stop"] for h in g["hooks"])
    assert set(settings["hooks"]) == {"Stop", "Notification", "UserPromptSubmit"}
    assert settings["hooks"]["Stop"][-1]["hooks"][0]["timeout"] == 75
    assert (tmp_path / "settings.json.bak").exists()

    setup.apply(path, remove=True)

    cleaned = json.loads(path.read_text())

    assert cleaned["hooks"] == {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}


def test_setup_refuses_a_settings_file_it_cannot_read(tmp_path):

    path = tmp_path / "settings.json"
    path.write_text("{ not json")

    with pytest.raises(ValueError):
        setup.apply(path, setup.hook_entries("py", setup.notify_script(), tmp_path))

    assert path.read_text() == "{ not json"


def test_hook_commands_use_forward_slashes():

    command = setup.hook_command("C:\\Python312\\python.exe", "C:\\p\\notify.py", "C:\\p\\data", 30)

    assert "\\" not in command and command.endswith("claude --relay 30")
