from types import SimpleNamespace

import pytest

from app.actions.pending_action_manager import PendingActionManager
from app.brain import gemini_client as client_module
from app.brain.brain import Brain
from app.brain.tool_context import ToolContext


@pytest.fixture
def brain(monkeypatch):

    class FakeGenaiClient:
        def __init__(self, **kwargs):
            self.models = SimpleNamespace(
                generate_content=lambda **kw: SimpleNamespace(
                    text="chat answer", function_calls=None, candidates=[]
                )
            )

    monkeypatch.setattr(client_module.genai, "Client", FakeGenaiClient)

    # Never touch the real schedule file
    monkeypatch.setattr(
        "app.brain.brain.ScheduleManager",
        lambda: SimpleNamespace(
            get_schedule=lambda d: [], add_schedule=lambda *a: None,
            delete_schedule=lambda d: None,
        ),
    )

    return Brain()


def ctx():

    context = ToolContext()
    context.pending_actions = PendingActionManager()

    return context


def ask(brain, text, context):

    return brain.chat(
        [{"role": "user", "content": text}], "", context
    )


def check_shape(result):

    assert {"response", "tool_used", "chat_success"} <= set(result)


def test_every_path_returns_the_full_result_shape(brain):

    context = ctx()

    for text in ["12*(5+8)", "what time is it", "tell me a joke"]:
        check_shape(ask(brain, text, context))


def test_confirmation_flow_end_to_end(brain):

    context = ctx()

    # Registry is attached to the context by the brain
    first = ask(brain, "close notepad", context)

    check_shape(first)
    assert "reply 'yes'" in first["response"].lower()
    assert context.pending_actions.current().exists()

    second = ask(brain, "no", context)

    check_shape(second)
    assert "cancelled" in second["response"].lower()
    assert not context.pending_actions.current().exists()


def test_unrelated_question_goes_to_chat(brain):

    result = ask(brain, "explain time complexity of quicksort", ctx())

    assert result["response"] == "chat answer"
    assert result["chat_success"]
