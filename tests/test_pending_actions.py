import pytest

from app.actions.pending_action_manager import PendingActionManager
from app.brain.engines.pending_action_engine import PendingActionEngine
from app.brain.tool_context import ToolContext
from app.tools.registry import Risk, Tool, ToolRegistry


def make_context(risk=Risk.CONFIRM):

    calls = []

    registry = ToolRegistry()
    registry.register(Tool(
        name="wipe",
        description="test tool",
        parameters={"target": {"type": "string"}},
        required=["target"],
        risk=risk,
        preview=lambda a: f"About to wipe {a['target']}.",
        handler=lambda context, target: calls.append(target) or (True, f"wiped {target}"),
    ))

    context = ToolContext()
    context.pending_actions = PendingActionManager()
    context.registry = registry

    return context, calls


def ask(context):

    return context.registry.execute("wipe", {"target": "x"}, context)


def test_risky_tool_waits_for_confirmation():

    context, calls = make_context()

    result = ask(context)

    assert result.needs_confirmation
    assert "About to wipe x" in result.message
    assert "yes" in result.message
    assert calls == []
    assert context.pending_actions.current().exists()


def test_dangerous_tool_shows_a_warning():

    context, _ = make_context(Risk.DANGEROUS)

    assert ask(context).message.startswith("Warning:")


def test_safe_tool_runs_immediately():

    context, calls = make_context(Risk.SAFE)

    result = ask(context)

    assert not result.needs_confirmation
    assert calls == ["x"]


@pytest.mark.parametrize("answer", ["yes", "Yes", "y", "ok", "go ahead", "yes."])
def test_yes_runs_the_tool(answer):

    context, calls = make_context()
    ask(context)

    result = PendingActionEngine().process(answer, context)

    assert result == {"handled": True, "response": "wiped x"}
    assert calls == ["x"]
    assert not context.pending_actions.current().exists()


@pytest.mark.parametrize("answer", ["no", "cancel", "nope"])
def test_no_cancels(answer):

    context, calls = make_context()
    ask(context)

    result = PendingActionEngine().process(answer, context)

    assert result["handled"]
    assert calls == []
    assert not context.pending_actions.current().exists()


def test_unrelated_message_is_not_trapped():

    context, calls = make_context()
    ask(context)

    result = PendingActionEngine().process("what is python", context)

    assert not result["handled"]
    assert calls == []
    assert not context.pending_actions.current().exists()


def test_confirmation_cannot_be_replayed():

    context, calls = make_context()
    ask(context)

    PendingActionEngine().process("yes", context)
    second = PendingActionEngine().process("yes", context)

    assert not second["handled"]
    assert calls == ["x"]


def test_no_pending_action_means_nothing_handled():

    context, _ = make_context()

    assert not PendingActionEngine().process("yes", context)["handled"]
