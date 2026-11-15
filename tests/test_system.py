from types import SimpleNamespace

import pytest

from app.actions.pending_action_manager import PendingActionManager
from app.brain.tool_context import ToolContext
from app.computer.background_watcher.watcher_manager import WatcherManager
from app.computer.computer_manager import ComputerManager
from app.computer.system_controls import (
    POWER_DELAY_SECONDS,
    VK_VOLUME_DOWN,
    VK_VOLUME_MUTE,
    VK_VOLUME_UP,
    SystemControls,
)
from app.computer.window_manager import WindowManager, process_name_for
from app.memory.user_profile import UserProfile
from app.tools.builtin_tools import build_default_registry
from app.tools.registry import Risk

import sys

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows behaviour")
mac_only = pytest.mark.skipif(sys.platform != "darwin", reason="macOS behaviour")


# ---------------------------------------------------------------
# WindowManager
# ---------------------------------------------------------------

TASKLIST = '"chrome.exe","123","Console","1","100,000 K"\n"Code.exe","456","Console","1","90,000 K"\n'


class FakeRun:
    """
    Pretends to be subprocess.run for tasklist / taskkill.
    """

    def __init__(self, still_running_after_close=False):
        self.commands = []
        self.running = {"chrome.exe", "Code.exe"}
        self.stubborn = still_running_after_close

    def __call__(self, command, **kwargs):

        self.commands.append(command)

        if command[0] == "tasklist":

            out = "".join(f'"{n}","1","Console","1","1 K"\n' for n in self.running)

            return SimpleNamespace(stdout=out, returncode=0)

        if command[0] == "taskkill" and not self.stubborn:
            self.running.discard(command[2])

        return SimpleNamespace(stdout="", returncode=0)


def make_windows(**kwargs):

    manager = WindowManager()
    manager.run = FakeRun(**kwargs)

    return manager


def test_is_running_ignores_case():

    manager = make_windows()

    assert manager.is_running("CHROME.EXE")
    assert not manager.is_running("notepad.exe")


def test_close_is_graceful_by_default():

    manager = make_windows()

    success, _ = manager.close("chrome.exe", wait_seconds=1)

    assert success
    assert ["taskkill", "/IM", "chrome.exe"] in manager.run.commands
    assert not any("/F" in c for c in manager.run.commands)


def test_force_close_adds_the_force_flag():

    manager = make_windows()

    manager.close("chrome.exe", force=True, wait_seconds=1)

    assert ["taskkill", "/IM", "chrome.exe", "/F"] in manager.run.commands


def test_close_reports_apps_that_are_not_running():

    success, message = make_windows().close("notepad.exe")

    assert not success
    assert "isn't running" in message


def test_close_reports_apps_that_refuse_to_close():

    manager = make_windows(still_running_after_close=True)

    success, message = manager.close("chrome.exe", wait_seconds=0.4)

    assert not success
    assert "force close" in message


def test_unknown_window_action():

    assert not make_windows().window_action("chrome", "explode")[0]


def test_process_name_for():

    assert process_name_for({"exe": r"C:\x\Code.exe"}) == "Code.exe"
    assert process_name_for({"shortcut": "a.lnk"}) is None


# ---------------------------------------------------------------
# ComputerManager.resolve_process
# ---------------------------------------------------------------

def make_computer(app=None):

    computer = ComputerManager()
    computer.app_manager = SimpleNamespace(find=lambda name: app)

    return computer


@windows_only
def test_known_apps_resolve_without_searching():

    assert make_computer().resolve_process("VS Code") == "Code.exe"


@windows_only
def test_discovered_apps_resolve_through_their_exe():

    computer = make_computer({"name": "Spotify", "exe": r"C:\a\Spotify.exe"})

    assert computer.resolve_process("spotify") == "Spotify.exe"
    assert computer.can_close("spotify")


def test_unknown_apps_cannot_be_closed():

    computer = make_computer(None)

    assert computer.resolve_process("zzz") is None
    assert not computer.can_close("zzz")


# ---------------------------------------------------------------
# SystemControls
# ---------------------------------------------------------------

def make_controls(tmp_path, **kwargs):

    keys = []
    commands = []

    def run(command, **kw):
        commands.append(command)
        return SimpleNamespace(returncode=kwargs.get("returncode", 0))

    controls = SystemControls(
        press_key=keys.append,
        run=run,
        grab=kwargs.get("grab"),
        pictures_dir=tmp_path,
    )

    return controls, keys, commands


def test_volume_steps(tmp_path):

    controls, keys, _ = make_controls(tmp_path)

    controls.change_volume("up", 3)
    controls.change_volume("down", 2)
    controls.toggle_mute()

    assert keys == [VK_VOLUME_UP] * 3 + [VK_VOLUME_DOWN] * 2 + [VK_VOLUME_MUTE]
    assert not controls.change_volume("sideways")[0]


def test_set_volume_goes_to_zero_then_up(tmp_path):

    controls, keys, _ = make_controls(tmp_path)

    controls.set_volume(40)

    assert keys.count(VK_VOLUME_DOWN) == 50
    assert keys.count(VK_VOLUME_UP) == 20


def test_volume_is_clamped(tmp_path):

    controls, keys, _ = make_controls(tmp_path)

    controls.set_volume(500)
    controls.change_volume("up", 9999)

    assert keys.count(VK_VOLUME_UP) == 50 + 50


def test_shutdown_starts_a_cancellable_countdown(tmp_path):

    controls, _, commands = make_controls(tmp_path)

    _, message = controls.power("shutdown")

    assert commands[-1] == ["shutdown", "/s", "/t", str(POWER_DELAY_SECONDS)]
    assert "cancel" in message

    controls.power("cancel")

    assert commands[-1] == ["shutdown", "/a"]
    assert not controls.power("explode")[0]


def test_brightness_failure_is_explained(tmp_path):

    controls, _, _ = make_controls(tmp_path, returncode=1)

    success, message = controls.set_brightness(50)

    assert not success
    assert "laptop" in message


def test_screenshot_is_saved(tmp_path):

    class Image:
        def save(self, path):
            path.write_bytes(b"png")

    controls, _, _ = make_controls(tmp_path, grab=lambda: Image())

    success, path = controls.screenshot()

    assert success
    assert path.endswith(".png")
    assert (tmp_path / path.split("\\")[-1]).exists()


def test_screenshot_errors_do_not_crash(tmp_path):

    def broken():
        raise OSError("no display")

    controls, _, _ = make_controls(tmp_path, grab=broken)

    assert not controls.screenshot()[0]


# ---------------------------------------------------------------
# New tools in the registry
# ---------------------------------------------------------------

class Stub:
    def __getattr__(self, name):
        return lambda *a, **k: (True, name)


@pytest.fixture
def registry_env(monkeypatch, tmp_path):

    monkeypatch.setattr(
        "app.tools.builtin_tools.ProfileStorage.save", lambda facts: None
    )

    seen = {}

    class Computer(Stub):
        def close_app(self, name, force=False):
            seen["close"] = (name, force)
            return True, "closed"

        def window_action(self, name, action):
            seen["window"] = (name, action)
            return True, "done"

    controls, keys, commands = make_controls(tmp_path)

    registry = build_default_registry(
        computer=Computer(), browser=Stub(), files=Stub(),
        search=Stub(), planner=Stub(), system=controls,
    )

    context = ToolContext()
    context.pending_actions = PendingActionManager()
    context.registry = registry
    context.profile = UserProfile()

    return context, seen, keys, commands


def test_close_application_can_force_after_confirmation(registry_env):

    context, seen, _, _ = registry_env

    first = context.registry.execute(
        "close_application", {"name": "chrome", "force": True}, context
    )

    assert first.needs_confirmation
    assert "force-close" in first.message
    assert "close" not in seen

    context.registry.execute(
        "close_application", {"name": "chrome", "force": True}, context, confirmed=True
    )

    assert seen["close"] == ("chrome", True)


def test_close_application_is_graceful_by_default(registry_env):

    context, seen, _, _ = registry_env

    context.registry.execute(
        "close_application", {"name": "chrome"}, context, confirmed=True
    )

    assert seen["close"] == ("chrome", False)


def test_window_action_runs_without_confirmation(registry_env):

    context, seen, _, _ = registry_env

    result = context.registry.execute(
        "window_action", {"name": "chrome", "action": "minimize"}, context
    )

    assert result.ok
    assert seen["window"] == ("chrome", "minimize")


def test_power_action_is_dangerous(registry_env):

    context, _, _, commands = registry_env

    assert context.registry.tools["power_action"].risk is Risk.DANGEROUS

    result = context.registry.execute("power_action", {"action": "restart"}, context)

    assert result.message.startswith("Warning:")
    assert commands == []


def test_volume_tool(registry_env):

    context, _, keys, _ = registry_env

    assert context.registry.execute("set_volume", {"level": 10}, context).ok
    assert context.registry.execute("set_volume", {"change": "mute"}, context).ok
    assert not context.registry.execute("set_volume", {}, context).ok


def test_memory_tools(registry_env):

    context, _, _, _ = registry_env

    run = lambda tool, args, confirmed=False: context.registry.execute(
        tool, args, context, confirmed=confirmed
    )

    assert "haven't stored" in run("list_memories", {}).message

    assert run("remember_fact", {"key": "Favorite Food", "value": "biryani"}).ok
    assert context.profile.get("favorite_food") == "biryani"
    assert "favorite_food: biryani" in run("list_memories", {}).message

    assert run("forget_fact", {"key": "favorite food"}).needs_confirmation
    assert context.profile.get("favorite_food") == "biryani"

    assert run("forget_fact", {"key": "favorite food"}, confirmed=True).ok
    assert context.profile.get("favorite_food") is None

    assert not run("forget_fact", {"key": "nothing"}, confirmed=True).ok


# ---------------------------------------------------------------
# Watcher
# ---------------------------------------------------------------

def test_watcher_refreshes_in_the_background_and_survives_errors():

    import threading

    calls = []
    done = threading.Event()

    def refresh(quiet=False):
        calls.append(quiet)
        if len(calls) == 1:
            raise RuntimeError("scan failed")
        done.set()

    manager = WatcherManager(SimpleNamespace(refresh_if_changed=refresh), interval=0.01)

    manager.start()
    manager.start()  # second start is a no-op

    assert done.wait(2)

    manager.stop()

    assert calls[:2] == [True, True]


# ---------------------------------------------------------------
# Process guessing and builtin process names
# ---------------------------------------------------------------

def test_guess_process_matches_running_programs():

    manager = make_windows()
    manager.run.running = {"Spotify.exe", "Code.exe", "CodeSetup.exe", "chrome.exe"}

    assert manager.guess_process("spotify") == "Spotify.exe"
    assert manager.guess_process("Google Chrome") is None
    assert manager.guess_process("co") is None      # too short to be safe
    assert manager.guess_process("nothing") is None


@windows_only
def test_builtin_calculator_closes_the_real_process():

    from app.computer.builtin_apps import builtin_applications

    calc = next(a for a in builtin_applications() if a["name"] == "Calculator")

    assert process_name_for(calc) == "CalculatorApp.exe"


# ---------------------------------------------------------------
# Vision
# ---------------------------------------------------------------

def test_capture_png_downscales_and_stays_in_memory(tmp_path):

    from PIL import Image

    controls, _, _ = make_controls(tmp_path, grab=lambda: Image.new("RGB", (3200, 1800), "white"))

    data = controls.capture_png(max_width=1600)

    assert data[:8] == b"\x89PNG\r\n\x1a\n"

    import io
    assert Image.open(io.BytesIO(data)).size == (1600, 900)
    assert list(tmp_path.iterdir()) == []


def test_look_at_screen_asks_vision_directly_by_default(registry_env, tmp_path):

    context, _, _, _ = registry_env

    asked = []

    registry = build_default_registry(
        computer=Stub(), browser=Stub(), files=Stub(), search=Stub(), planner=Stub(),
        vision=lambda question: asked.append(question) or "a terminal showing an error",
    )

    result = registry.execute("look_at_screen", {"question": "what error?"}, context)

    assert result.message == "a terminal showing an error"
    assert asked == ["what error?"]
