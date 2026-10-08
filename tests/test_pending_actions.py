from app.actions.pending_action_manager import PendingActionManager
from app.brain.engines.pending_action_engine import PendingActionEngine
from app.brain.tool_context import ToolContext


class FakeFileManager:

    def __init__(self):
        self.calls = []

    def rename(self, path, new_name):
        self.calls.append((path, new_name))
        return True, "renamed"


class FakeIndexer:

    saved = False

    def save(self):
        self.saved = True


def make_context():

    context = ToolContext()
    context.pending_actions = PendingActionManager()
    context.file_manager = FakeFileManager()
    context.file_indexer = FakeIndexer()

    context.pending_actions.start(
        action="rename",
        matches=[{"path": "a.txt"}, {"path": "b.txt"}],
        data={"new_name": "c.txt"},
    )

    return context


def test_start_activates_the_pending_action():

    context = make_context()

    assert context.pending_actions.current().exists()


def test_choosing_a_number_renames_that_item():

    context = make_context()

    result = PendingActionEngine().process("2", context)

    assert result == {"handled": True, "response": "renamed"}
    assert context.file_manager.calls == [("b.txt", "c.txt")]
    assert context.file_indexer.saved
    assert not context.pending_actions.current().exists()


def test_invalid_number_keeps_waiting():

    context = make_context()

    result = PendingActionEngine().process("9", context)

    assert result["handled"]
    assert context.pending_actions.current().exists()


def test_cancel():

    context = make_context()

    result = PendingActionEngine().process("cancel", context)

    assert result["handled"]
    assert not context.pending_actions.current().exists()
    assert context.file_manager.calls == []


def test_unrelated_message_is_not_trapped():

    context = make_context()

    result = PendingActionEngine().process("what is python", context)

    assert not result["handled"]
    assert not context.pending_actions.current().exists()
