from types import SimpleNamespace

import pytest

from app.actions.pending_action_manager import PendingActionManager
from app.brain.tool_context import ToolContext
from app.file.file_manager import FileManager
from app.file.path_guard import PathGuard
from app.file.program_info import describe, from_internet, signature
from app.file.search import FileSearch
from app.tools.builtin_tools import build_default_registry
from tests.test_tools import FakeBrowser, FakeComputer, FakePlanner

import sys

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows behaviour")
mac_only = pytest.mark.skipif(sys.platform != "darwin", reason="macOS behaviour")


# ---------------------------------------------------------------
# program_info
# ---------------------------------------------------------------

def fake_run(stdout):

    return lambda *a, **k: SimpleNamespace(stdout=stdout, returncode=0)


def test_signed_programs_show_their_publisher():

    run = fake_run('{"status":"Valid","subject":"CN=Microsoft Corporation, O=Microsoft, C=US"}')

    assert signature("x.exe", run=run) == ("signed", "Microsoft Corporation")


def test_unsigned_and_unknown_programs():

    assert signature("x.exe", run=fake_run('{"status":"NotSigned","subject":""}')) == ("unsigned", "")
    assert signature("x.exe", run=fake_run("garbage"))[0] == "unknown"

    def boom(*a, **k):
        raise OSError("no powershell")

    assert signature("x.exe", run=boom)[0] == "unknown"


def test_description_mentions_downloads_and_missing_signatures():

    text = describe("x.exe", sig=lambda p: ("unsigned", ""), internet=lambda p: True)

    assert text == "NOT digitally signed, downloaded from the internet"

    assert describe("x.exe", sig=lambda p: ("signed", "Valve"), internet=lambda p: False) == "signed by Valve"


@windows_only
def test_zone_identifier_detection(tmp_path):

    plain = tmp_path / "a.exe"
    plain.write_text("x")

    assert from_internet(plain) is False

    marked = tmp_path / "b.exe"
    marked.write_text("x")

    with open(str(marked) + ":Zone.Identifier", "w") as f:
        f.write("[ZoneTransfer]\nZoneId=3\n")

    assert from_internet(marked) is True


# ---------------------------------------------------------------
# launch_program
# ---------------------------------------------------------------

class LaunchFiles(FileManager):

    def __init__(self):
        super().__init__()
        self.opened = []

    def open_file(self, path):
        self.opened.append(str(path))
        return True, f"Opening '{path.name}'..."


@pytest.fixture
def env(tmp_path):

    home = tmp_path / "user"
    (home / "Downloads").mkdir(parents=True)

    guard = PathGuard(home=home, system_dirs=[tmp_path / "Windows"])

    files = LaunchFiles()

    context = ToolContext()
    context.pending_actions = PendingActionManager()
    context.registry = build_default_registry(
        computer=FakeComputer(), browser=FakeBrowser(), files=files,
        search=FileSearch(guard, index_query=lambda t, n: [], home=home),
        planner=FakePlanner(), guard=guard,
    )

    return context, files, home


def launch(context, path, confirmed=False):

    return context.registry.execute("launch_program", {"path": str(path)}, context, confirmed=confirmed)


@windows_only
def test_launching_asks_first_and_shows_the_facts(env, monkeypatch):

    context, files, home = env

    game = home / "Downloads" / "game.exe"
    game.write_text("x")

    monkeypatch.setattr(
        "app.tools.file_tools.describe", lambda p: "x", raising=False
    )

    result = launch(context, game)

    assert result.needs_confirmation
    assert str(game) in result.message
    assert "signature" in result.message or "signed" in result.message
    assert files.opened == []


@windows_only
def test_one_always_covers_launching_for_the_session(env):

    context, files, home = env

    game = home / "Downloads" / "game.exe"
    game.write_text("x")

    assert "always" in launch(context, game).message.lower()

    assert context.registry.trust("launch_program")

    result = launch(context, game)

    assert result.ok and files.opened == [str(game.resolve())]


@windows_only
@pytest.mark.parametrize("name", ["setup.exe", "tool.lnk", "app.msi", "run.bat", "run.cmd"])
def test_programs_can_be_launched(env, name):

    context, files, home = env

    path = home / "Downloads" / name
    path.write_text("x")

    assert launch(context, path, confirmed=True).ok
    assert files.opened == [str(path.resolve())]


@pytest.mark.parametrize("name", ["x.ps1", "x.vbs", "x.js", "x.reg", "x.dll", "x.scr"])
def test_scripts_and_libraries_are_never_launched(env, name):

    context, files, home = env

    path = home / "Downloads" / name
    path.write_text("x")

    result = launch(context, path, confirmed=True)

    assert not result.ok and files.opened == []


def test_documents_and_missing_files_are_not_programs(env):

    context, files, home = env

    doc = home / "Downloads" / "a.pdf"
    doc.write_text("x")

    assert "open_file" in launch(context, doc, confirmed=True).message
    assert not launch(context, home / "Downloads" / "ghost.exe", confirmed=True).ok
    assert files.opened == []


def test_secrets_cannot_be_launched(env):

    context, files, home = env

    key = home / ".ssh" / "evil.exe"
    key.parent.mkdir()
    key.write_text("x")

    assert not launch(context, key, confirmed=True).ok


# ---------------------------------------------------------------
# Screen policy
# ---------------------------------------------------------------

def test_looking_at_the_screen_is_free_unless_the_user_wants_to_be_asked(tmp_path):

    asked = []
    policy = {"confirm": False}

    context = ToolContext()
    context.pending_actions = PendingActionManager()

    guard = PathGuard(home=tmp_path, system_dirs=[])

    context.registry = build_default_registry(
        computer=FakeComputer(), browser=FakeBrowser(), files=FileManager(),
        search=FileSearch(guard, index_query=lambda t, n: [], home=tmp_path),
        planner=FakePlanner(), guard=guard,
        vision=lambda q: asked.append(q) or "a terminal", screen_policy=policy,
    )

    assert context.registry.execute("look_at_screen", {"question": "what?"}, context).ok
    assert asked == ["what?"]

    policy["confirm"] = True

    result = context.registry.execute("look_at_screen", {"question": "again"}, context)

    assert result.needs_confirmation
    assert asked == ["what?"]


@mac_only
def test_mac_apps_and_installers_can_be_launched(env):

    context, files, home = env

    bundle = home / "Downloads" / "Tool.app"
    (bundle / "Contents").mkdir(parents=True)

    installer = home / "Downloads" / "setup.pkg"
    installer.write_text("x")

    assert launch(context, bundle, confirmed=True).ok
    assert launch(context, installer, confirmed=True).ok
    assert files.opened == [str(bundle.resolve()), str(installer.resolve())]


@mac_only
def test_mac_quarantine_flag_is_detected(tmp_path):

    import subprocess

    plain = tmp_path / "a.dmg"
    plain.write_text("x")

    assert from_internet(plain) is False

    subprocess.run(["xattr", "-w", "com.apple.quarantine", "0081;0;Safari;", str(plain)], check=True)

    assert from_internet(plain) is True
