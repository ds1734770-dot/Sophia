import pytest

from app.actions.pending_action_manager import PendingActionManager
from app.brain.tool_context import ToolContext
from app.computer.screen_control import ScreenControl, parse_point
from app.file.file_manager import FileManager
from app.file.path_guard import PathGuard
from app.file.search import FileSearch
from app.tools.builtin_tools import build_default_registry
from app.tools.undo import UndoStack
from tests.test_tools import FakeBrowser, FakeComputer, FakePlanner


# ---------------------------------------------------------------
# parse_point
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ('{"point": [500, 250]}', (500.0, 250.0)),
        ('{"point": [0, 1000]}', (0.0, 1000.0)),
        ('{"point": null}', None),
        ('{"point": [1, 2, 3]}', None),
        ('{"point": [1500, 10]}', None),
        ('{"point": ["a", "b"]}', None),
        ("not json", None),
        ("[1, 2]", None),
        (None, None),
    ],
)
def test_parse_point(text, expected):

    assert parse_point(text) == expected


# ---------------------------------------------------------------
# ScreenControl
# ---------------------------------------------------------------

class FakeBackend:

    def __init__(self):
        self.events = []

    def size(self):
        return 2000, 1000

    def click(self, x, y, button="left", double=False):
        self.events.append(("click", x, y, button, double))

    def write(self, text):
        self.events.append(("write", text))

    def hotkey(self, *keys):
        self.events.append(("hotkey", keys))

    def press(self, key):
        self.events.append(("press", key))

    def scroll(self, amount):
        self.events.append(("scroll", amount))


class FakeClipboard:

    def __init__(self):
        self.text = "old"

    def get(self):
        return self.text

    def set(self, text):
        self.text = text


def make_screen(answer='{"point": [500, 250]}', clipboard=None):

    backend = FakeBackend()

    asked = []

    def locate(description, png):
        asked.append((description, png))

        if isinstance(answer, Exception):
            raise answer

        return answer

    screen = ScreenControl(
        capture_png=lambda: b"PNG",
        locate=locate,
        backend=backend,
        clipboard=clipboard,
    )

    return screen, backend, asked


def test_click_converts_the_point_to_screen_pixels():

    screen, backend, asked = make_screen()

    ok, message = screen.click_on("the Send button")

    assert ok
    assert asked == [("the Send button", b"PNG")]
    assert backend.events == [("click", 500, 500, "left", False)]
    assert "(500, 500)" in message


def test_click_options_are_passed_on():

    screen, backend, _ = make_screen()

    screen.click_on("file", button="right", double=True)

    assert backend.events == [("click", 500, 500, "right", True)]


def test_nothing_is_clicked_when_the_element_is_not_found_or_vision_fails():

    screen, backend, _ = make_screen('{"point": null}')

    ok, message = screen.click_on("the unicorn")

    assert not ok and "couldn't see" in message
    assert backend.events == []

    screen, backend, _ = make_screen(RuntimeError("quota"))

    assert not screen.click_on("x")[0]
    assert backend.events == []


def test_typing_ascii_and_enter():

    screen, backend, _ = make_screen()

    assert screen.type_text("hello world", press_enter=True)[0]

    assert backend.events == [("write", "hello world"), ("press", "enter")]


def test_non_ascii_text_is_pasted_and_the_clipboard_restored():

    clip = FakeClipboard()

    screen, backend, _ = make_screen(clipboard=clip)

    assert screen.type_text("నమస్తే")[0]

    assert backend.events == [("hotkey", ("ctrl", "v"))]
    assert clip.text == "old"

    screen2, _, _ = make_screen(clipboard=None)

    assert not screen2.type_text("నమస్తే")[0]


def test_typing_has_a_length_limit():

    screen, backend, _ = make_screen()

    assert not screen.type_text("x" * 5000)[0]
    assert backend.events == []


@pytest.mark.parametrize(
    "keys, event",
    [
        ("enter", ("press", "enter")),
        ("Ctrl+C", ("hotkey", ("ctrl", "c"))),
        ("alt + tab", ("hotkey", ("alt", "tab"))),
    ],
)
def test_key_presses(keys, event):

    screen, backend, _ = make_screen()

    assert screen.press_keys(keys)[0]
    assert backend.events == [event]


@pytest.mark.parametrize("keys", ["", "a+b+c+d+e", "ctrl+alt+delete", "win+l", "ctrl+shift+esc"])
def test_bad_or_blocked_key_presses(keys):

    screen, backend, _ = make_screen()

    assert not screen.press_keys(keys)[0]
    assert backend.events == []


def test_scrolling():

    screen, backend, _ = make_screen()

    screen.scroll("down", 2)
    screen.scroll("up", 999)

    assert backend.events == [("scroll", -240), ("scroll", 3600)]


# ---------------------------------------------------------------
# Screen tools in the registry
# ---------------------------------------------------------------

def make_registry(tmp_path, screen=None, undo=None):

    home = tmp_path / "user"

    for name in ("Desktop", "Documents", "Downloads"):
        (home / name).mkdir(parents=True)

    guard = PathGuard(home=home, system_dirs=[tmp_path / "Windows"])

    files = FileManager()
    files.home = home

    context = ToolContext()
    context.pending_actions = PendingActionManager()
    context.registry = build_default_registry(
        computer=FakeComputer(), browser=FakeBrowser(), files=files,
        search=FileSearch(guard, index_query=lambda t, n: [], home=home),
        planner=FakePlanner(), guard=guard, screen=screen, undo=undo,
    )

    return context, home


def test_screen_actions_ask_first_and_can_be_trusted(tmp_path):

    screen, backend, _ = make_screen()

    context, _ = make_registry(tmp_path, screen=screen)

    first = context.registry.execute("click_on_screen", {"target": "Send"}, context)

    assert first.needs_confirmation
    assert "click on 'Send'" in first.message
    assert "always" in first.message.lower()
    assert backend.events == []

    assert context.registry.trust("click_on_screen")

    again = context.registry.execute("click_on_screen", {"target": "Send"}, context)

    assert again.ok and backend.events


def test_scrolling_needs_no_confirmation(tmp_path):

    screen, backend, _ = make_screen()

    context, _ = make_registry(tmp_path, screen=screen)

    assert context.registry.execute("scroll_screen", {"direction": "down"}, context).ok


def test_typing_shows_what_will_be_typed(tmp_path):

    screen, _, _ = make_screen()

    context, _ = make_registry(tmp_path, screen=screen)

    message = context.registry.execute(
        "type_text", {"text": "hello", "press_enter": True}, context
    ).message

    assert 'type "hello" and press Enter' in message


# ---------------------------------------------------------------
# Undo
# ---------------------------------------------------------------

def test_undo_stack():

    stack = UndoStack()

    assert stack.undo() == (False, "There is nothing to undo.")
    assert stack.describe() == "Nothing to undo."

    log = []

    stack.push("first", lambda: log.append("1") or (True, ""))
    stack.push("second", lambda: log.append("2") or (True, "done"))

    assert stack.peek() == "second"

    ok, message = stack.undo()

    assert ok and message == "Undone: second. done"
    assert stack.undo()[0]
    assert log == ["2", "1"]


def test_failed_undo_reports_why():

    stack = UndoStack()

    stack.push("x", lambda: (False, "gone"))
    stack.push("y", lambda: 1 / 0)

    assert "couldn't undo 'y'" in stack.undo()[1]
    assert "gone" in stack.undo()[1]


def undo_run(context, tool, confirmed=True, **args):

    return context.registry.execute(tool, args, context, confirmed=confirmed)


def test_rename_can_be_undone(tmp_path):

    context, home = make_registry(tmp_path, undo=UndoStack())

    target = home / "Documents" / "old.txt"
    target.write_text("x")

    undo_run(context, "rename_file", path=str(target), new_name="new.txt")
    assert (home / "Documents" / "new.txt").exists()

    assert undo_run(context, "undo_last_action").ok
    assert target.exists() and not (home / "Documents" / "new.txt").exists()


def test_move_and_copy_can_be_undone(tmp_path):

    context, home = make_registry(tmp_path, undo=UndoStack())

    source = home / "Downloads" / "a.txt"
    source.write_text("x")
    (home / "Documents" / "box").mkdir()

    undo_run(context, "move_file", source=str(source), destination=str(home / "Documents" / "box"))
    assert (home / "Documents" / "box" / "a.txt").exists()

    undo_run(context, "undo_last_action")
    assert source.exists() and not (home / "Documents" / "box" / "a.txt").exists()


def test_new_folders_and_files_can_be_undone(tmp_path):

    context, home = make_registry(tmp_path, undo=UndoStack())

    undo_run(context, "create_folder", name="Fresh", location="Desktop")
    assert (home / "Desktop" / "Fresh").is_dir()

    assert undo_run(context, "undo_last_action").ok
    assert not (home / "Desktop" / "Fresh").exists()


def test_a_non_empty_folder_is_not_removed_by_undo(tmp_path):

    context, home = make_registry(tmp_path, undo=UndoStack())

    undo_run(context, "create_folder", name="Fresh", location="Desktop")
    (home / "Desktop" / "Fresh" / "keep.txt").write_text("x")

    result = undo_run(context, "undo_last_action")

    assert not result.ok
    assert (home / "Desktop" / "Fresh" / "keep.txt").exists()


def test_undo_asks_first_and_says_what_it_will_undo(tmp_path):

    context, home = make_registry(tmp_path, undo=UndoStack())

    target = home / "Documents" / "old.txt"
    target.write_text("x")

    undo_run(context, "rename_file", path=str(target), new_name="new.txt")

    asked = context.registry.execute("undo_last_action", {}, context)

    assert asked.needs_confirmation
    assert "rename old.txt to new.txt" in asked.message
    assert (home / "Documents" / "new.txt").exists()
