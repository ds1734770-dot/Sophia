
import pytest

from app.actions.pending_action_manager import PendingActionManager
from app.brain.tool_context import ToolContext
from app.file.path_guard import is_safe_name, resolve_allowed
from app.tools.builtin_tools import build_default_registry
from app.tools.registry import Risk, Tool, ToolRegistry


# ---------------------------------------------------------------
# Path guard
# ---------------------------------------------------------------

@pytest.fixture
def home(tmp_path):

    for name in ("Desktop", "Documents", "Downloads"):
        (tmp_path / name).mkdir()

    (tmp_path / "secret.txt").write_text("x")

    return tmp_path


def test_paths_inside_allowed_folders_pass(home):

    target = home / "Documents" / "a.txt"
    target.write_text("x")

    assert resolve_allowed(target, home) == target.resolve()


@pytest.mark.parametrize(
    "relative",
    [
        "secret.txt",
        "Documents",                          # the root itself
        "Documents/../secret.txt",            # traversal
        "../outside.txt",
    ],
)
def test_paths_outside_are_rejected(home, relative):

    assert resolve_allowed(home / relative, home) is None


@pytest.mark.parametrize(
    "name, ok",
    [
        ("notes.txt", True),
        ("My Folder", True),
        ("..", False),
        ("a/b", False),
        ("a\\b", False),
        ("C:evil", False),
        ("", False),
        ("trailing.", False),
    ],
)
def test_safe_names(name, ok):

    assert is_safe_name(name) is ok


# ---------------------------------------------------------------
# Registry
# ---------------------------------------------------------------

class FakeComputer:

    def __init__(self):
        self.closed = []

    def open_app(self, name):
        return True, f"Opening {name}..."

    def close_app(self, name):
        self.closed.append(name)
        return True, f"Closing {name}..."

    def open_folder(self, name):
        return True, "ok"

    def close_folder(self, name):
        return True, "ok"

    def lock(self):
        return True, "Locking..."


class FakeFiles:

    def __init__(self):
        self.renamed = []
        self.deleted = []

    def create_folder(self, name, location=None):
        return True, f"created {name}"

    def rename(self, path, new_name):
        self.renamed.append((str(path), new_name))
        return True, "renamed"

    def delete(self, path):
        self.deleted.append(str(path))
        return True, "trashed"

    def open_file(self, path):
        return True, f"opening {path.name}"


class FakeIndexer:

    def save(self):
        pass

    def search(self, query):
        return False, "No matching files found."


class FakeBrowser:

    def __init__(self):
        self.urls = []

    def open_website(self, name):
        return False, f"I don't know the website '{name}'."

    def open_url(self, url):
        self.urls.append(url)
        return True, f"Opening {url}..."

    def google_search(self, query):
        return True, f"google {query}"

    def youtube_search(self, query):
        return True, f"youtube {query}"


class FakePlanner:

    def __init__(self):
        self.items = {}

    def get_schedule(self, date):
        return self.items.get(date, [])

    def add_schedule(self, date, time, task):
        self.items.setdefault(date, []).append({"time": time, "task": task})

    def delete_schedule(self, date):
        self.items.pop(date, None)


@pytest.fixture
def env(monkeypatch, home):

    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: home))

    parts = dict(
        computer=FakeComputer(),
        browser=FakeBrowser(),
        files=FakeFiles(),
        indexer=FakeIndexer(),
        planner=FakePlanner(),
    )

    context = ToolContext()
    context.pending_actions = PendingActionManager()
    context.registry = build_default_registry(**parts)

    return context, parts, home


def run(env, tool, **args):

    context, _, _ = env

    return context.registry.execute(tool, args, context)


def test_every_tool_has_a_declaration_and_tier(env):

    registry = env[0].registry

    assert len(registry.declarations()) == len(registry.names())

    tiers = {name: registry.tools[name].risk for name in registry.names()}

    assert tiers["delete_file"] is Risk.DANGEROUS
    assert tiers["close_application"] is Risk.CONFIRM
    assert tiers["rename_file"] is Risk.CONFIRM
    assert tiers["open_file"] is Risk.CONFIRM
    assert tiers["open_application"] is Risk.SAFE


def test_unknown_missing_and_extra_arguments(env):

    assert not run(env, "nope").ok
    assert "Missing" in run(env, "calculate").message
    assert "Unexpected" in run(env, "calculate", expression="1+1", extra="x").message


def test_calculate(env):

    assert run(env, "calculate", expression="2+3*4").message == "14"
    assert not run(env, "calculate", expression="9**9**9**9").ok
    assert not run(env, "calculate", expression="__import__('os')").ok


def test_close_application_needs_confirmation(env):

    _, parts, _ = env

    result = run(env, "close_application", name="notepad")

    assert result.needs_confirmation
    assert parts["computer"].closed == []


def test_rename_requires_confirmation_then_runs(env):

    context, parts, home = env

    target = home / "Documents" / "old.txt"
    target.write_text("x")

    first = run(env, "rename_file", path=str(target), new_name="new.txt")

    assert first.needs_confirmation
    assert parts["files"].renamed == []

    confirmed = context.registry.execute(
        "rename_file",
        {"path": str(target), "new_name": "new.txt"},
        context,
        confirmed=True,
    )

    assert confirmed.ok
    assert parts["files"].renamed == [(str(target.resolve()), "new.txt")]


def test_rename_refuses_unsafe_targets(env):

    context, parts, home = env

    outside = home / "secret.txt"
    inside = home / "Documents" / "a.txt"
    inside.write_text("x")

    def confirmed(**args):
        return context.registry.execute("rename_file", args, context, confirmed=True)

    assert not confirmed(path=str(outside), new_name="x.txt").ok
    assert not confirmed(path=str(inside), new_name="..\\..\\evil.txt").ok
    assert not confirmed(path=str(home / "Documents" / "missing.txt"), new_name="x").ok
    assert parts["files"].renamed == []


def test_delete_goes_to_recycle_bin_after_confirmation(env):

    context, parts, home = env

    target = home / "Downloads" / "junk.txt"
    target.write_text("x")

    first = run(env, "delete_file", path=str(target))

    assert first.needs_confirmation
    assert first.message.startswith("Warning:")
    assert parts["files"].deleted == []

    context.registry.execute("delete_file", {"path": str(target)}, context, confirmed=True)

    assert parts["files"].deleted == [str(target.resolve())]


def test_delete_refuses_outside_allowed_folders(env):

    context, parts, home = env

    result = context.registry.execute(
        "delete_file", {"path": str(home / "secret.txt")}, context, confirmed=True
    )

    assert not result.ok
    assert parts["files"].deleted == []


def test_open_file_blocks_programs(env):

    context, _, home = env

    script = home / "Downloads" / "setup.exe"
    script.write_text("x")
    note = home / "Downloads" / "note.txt"
    note.write_text("x")

    def confirmed(path):
        return context.registry.execute(
            "open_file", {"path": str(path)}, context, confirmed=True
        )

    assert not confirmed(script).ok
    assert confirmed(note).ok


def test_create_folder_rules(env):

    assert run(env, "create_folder", name="Projects").ok
    assert run(env, "create_folder", name="Projects", location="Desktop").ok
    assert not run(env, "create_folder", name="../evil").ok
    assert not run(env, "create_folder", name="x", location="C:\\Windows").ok


def test_open_website_accepts_only_web_links(env):

    _, parts, _ = env

    assert run(env, "open_website", target="https://example.com/a").ok
    assert run(env, "open_website", target="example.com").ok
    assert not run(env, "open_website", target="file:///C:/Windows/system32/calc.exe").ok
    assert not run(env, "open_website", target="javascript:alert(1)").ok
    assert parts["browser"].urls == ["https://example.com/a", "https://example.com"]


def test_web_search(env):

    assert run(env, "web_search", query="python").message == "google python"
    assert run(env, "web_search", query="lofi", site="youtube").message == "youtube lofi"


def test_schedule_tools(env):

    assert run(env, "add_schedule", date="2026-10-09", time="18:30", task="Gym").ok
    assert "already" in run(env, "add_schedule", date="2026-10-09", time="18:30", task="Gym").message
    assert not run(env, "add_schedule", date="9 Oct", time="18:30", task="x").ok
    assert not run(env, "add_schedule", date="2026-10-09", time="6pm", task="x").ok

    assert "18:30 Gym" in run(env, "get_schedule", date="2026-10-09").message
    assert "Nothing" in run(env, "get_schedule", date="2026-10-10").message

    assert run(env, "clear_schedule", date="2026-10-09").needs_confirmation


def test_handler_errors_become_failed_results():

    registry = ToolRegistry()
    registry.register(Tool(
        name="boom",
        description="x",
        handler=lambda context: 1 / 0,
    ))

    result = registry.execute("boom", {}, None)

    assert not result.ok
    assert "failed" in result.message
