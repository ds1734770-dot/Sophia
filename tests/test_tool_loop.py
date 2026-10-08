from types import SimpleNamespace

from google.genai import types

from app.actions.pending_action_manager import PendingActionManager
from app.brain import gemini_client as module
from app.brain.tool_context import ToolContext
from app.tools.registry import Risk, Tool, ToolRegistry


def function_call(name, args):

    return types.FunctionCall(name=name, args=args)


def model_reply(text=None, calls=None):
    """
    A fake Gemini response: either text or function calls.
    """

    parts = []

    for call in calls or []:
        parts.append(types.Part(function_call=call))

    if text:
        parts.append(types.Part(text=text))

    return SimpleNamespace(
        text=text,
        function_calls=calls or None,
        candidates=[SimpleNamespace(
            content=types.Content(role="model", parts=parts)
        )],
    )


class ScriptedModels:

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def generate_content(self, model, contents, config):
        self.requests.append((list(contents), config))
        return self.replies.pop(0)


def make(monkeypatch, replies, risk=Risk.SAFE):

    models = ScriptedModels(replies)

    class FakeGenaiClient:
        def __init__(self, **kwargs):
            self.models = models

    monkeypatch.setattr(module.genai, "Client", FakeGenaiClient)
    monkeypatch.setattr(module.GeminiClient, "_http", {})

    ran = []

    registry = ToolRegistry()
    registry.register(Tool(
        name="open_application",
        description="open",
        parameters={"name": {"type": "string"}},
        required=["name"],
        risk=risk,
        preview=lambda a: f"About to open {a['name']}.",
        handler=lambda context, name: ran.append(name) or (True, f"Opening {name}..."),
    ))

    context = ToolContext()
    context.pending_actions = PendingActionManager()
    context.registry = registry

    return module.GeminiClient(), models, registry, context, ran


CONVERSATION = [
    {"role": "system", "content": "be Sophia"},
    {"role": "user", "content": "open notepad"},
]


def test_plain_answer_uses_no_tool(monkeypatch):

    client, models, registry, context, ran = make(
        monkeypatch, [model_reply(text="Hello!")]
    )

    text, used = client.generate_with_tools(CONVERSATION, "", registry, context)

    assert (text, used) == ("Hello!", False)
    assert ran == []


def test_tool_call_is_executed_and_result_returned_to_model(monkeypatch):

    client, models, registry, context, ran = make(monkeypatch, [
        model_reply(calls=[function_call("open_application", {"name": "notepad"})]),
        model_reply(text="Opened Notepad."),
    ])

    text, used = client.generate_with_tools(CONVERSATION, "", registry, context)

    assert (text, used) == ("Opened Notepad.", True)
    assert ran == ["notepad"]

    # The second request carries the tool result back to the model
    contents, config = models.requests[1]
    answer = contents[-1].parts[0].function_response

    assert answer.name == "open_application"
    assert answer.response == {"ok": True, "result": "Opening notepad..."}

    # Tools are declared and automatic calling is off
    assert config.automatic_function_calling.disable
    assert config.tools[0].function_declarations[0].name == "open_application"


def test_risky_tool_stops_the_loop_with_a_question(monkeypatch):

    client, models, registry, context, ran = make(
        monkeypatch,
        [model_reply(calls=[function_call("open_application", {"name": "notepad"})])],
        risk=Risk.CONFIRM,
    )

    text, used = client.generate_with_tools(CONVERSATION, "", registry, context)

    assert used
    assert "About to open notepad." in text
    assert "yes" in text
    assert ran == []
    assert len(models.requests) == 1
    assert context.pending_actions.current().exists()


def test_bad_arguments_are_reported_not_crashed(monkeypatch):

    client, models, registry, context, ran = make(monkeypatch, [
        model_reply(calls=[function_call("open_application", {})]),
        model_reply(text="Sorry, which app?"),
    ])

    text, _ = client.generate_with_tools(CONVERSATION, "", registry, context)

    assert text == "Sorry, which app?"
    assert ran == []

    result = models.requests[1][0][-1].parts[0].function_response.response

    assert result["ok"] is False


def test_tool_loop_is_bounded(monkeypatch):

    endless = [
        model_reply(calls=[function_call("open_application", {"name": "x"})])
        for _ in range(20)
    ]

    client, models, registry, context, ran = make(monkeypatch, endless)

    text, used = client.generate_with_tools(CONVERSATION, "", registry, context)

    assert used
    assert "smaller requests" in text
    assert len(models.requests) == client.MAX_TOOL_STEPS


def test_thinking_setting_is_dropped_when_a_model_rejects_it(monkeypatch):

    from app.brain.gemini_client import GeminiClient

    seen = []

    class Models:
        def generate_content(self, model, contents, config):
            seen.append(config.thinking_config)
            if config.thinking_config is not None:
                raise RuntimeError("400 INVALID_ARGUMENT: thinking level is not supported")
            return model_reply("hi")

    class FakeGenaiClient:
        def __init__(self, **kwargs):
            self.models = Models()

    monkeypatch.setattr(module.genai, "Client", FakeGenaiClient)
    monkeypatch.setattr(module.GeminiClient, "_http", {})

    client = GeminiClient()

    assert client.generate([{"role": "user", "content": "x"}], "").text == "hi"
    assert seen[0] is not None and seen[1] is None
    assert client.no_thinking == {'main'} or len(client.no_thinking) == 1


def test_read_only_calls_run_together_and_in_order(monkeypatch):

    import threading
    import time as _time

    from app.brain.gemini_client import GeminiClient

    started = []
    overlap = []

    def slow(context, query):
        started.append(query)
        _time.sleep(0.2)
        overlap.append(len(started))
        return True, query.upper()

    registry = ToolRegistry()
    registry.register(Tool(
        name="web_search", description="s",
        parameters={"query": {"type": "string"}}, required=["query"],
        handler=slow,
    ))

    calls = [function_call("web_search", {"query": q}) for q in ("a", "b", "c")]

    t = _time.time()
    results = GeminiClient._run_calls(calls, registry, ToolContext())

    assert [r.message for r in results] == ["A", "B", "C"]
    assert _time.time() - t < 0.5
    assert max(overlap) == 3
