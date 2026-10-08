from types import SimpleNamespace

import pytest

from app import sophia as sophia_module
from app.sophia import Sophia


@pytest.fixture
def sophia(monkeypatch, tmp_path):

    # No real files, apps or AI
    for storage in ("MemoryStorage", "ProfileStorage", "SummaryStorage"):
        monkeypatch.setattr(f"app.sophia.{storage}.save", lambda *a, **k: None)

    monkeypatch.setattr("app.sophia.MemoryStorage.load", lambda: [])
    monkeypatch.setattr("app.sophia.ProfileStorage.load", lambda: {})
    monkeypatch.setattr("app.sophia.SummaryStorage.load", lambda: "")

    class FakeBrain:
        def __init__(self):
            self.replies = []
            self.tool_engine = SimpleNamespace(file_manager=None, indexer=None)
            self.extracted = []

        def chat(self, conversation, system_instruction, context):
            self.last_conversation = conversation
            self.last_instruction = system_instruction
            return self.replies.pop(0)

        def extract_memory(self, text):
            self.extracted.append(text)
            return {"city": "Vizag"}

        def summarize(self, previous, messages):
            return "summary"

    class FakeApps:
        def initialize(self):
            pass

    monkeypatch.setattr(sophia_module, "Brain", FakeBrain)
    monkeypatch.setattr(sophia_module, "ApplicationManager", FakeApps)

    return Sophia()


def reply(text, tool_used=False, ok=True):

    return {"response": text, "tool_used": tool_used, "chat_success": ok}


def test_respond_returns_the_reply_and_updates_history(sophia):

    sophia.brain.replies.append(reply("hello!"))

    result = sophia.respond("  hi there  ")

    assert result == {"response": "hello!", "tool_used": False}
    assert [m["content"] for m in sophia.memory.get_history()] == ["hi there", "hello!"]
    assert "Current local date and time" in sophia.brain.last_instruction


def test_personal_statements_update_the_profile(sophia):

    sophia.brain.replies.append(reply("nice"))

    sophia.respond("I live in Vizag")

    assert sophia.profile.get("city") == "Vizag"


def test_no_extraction_after_tool_use_or_failure_or_questions(sophia):

    sophia.brain.replies += [reply("done", tool_used=True), reply("err", ok=False), reply("a")]

    sophia.respond("I live in Vizag")
    sophia.respond("I live in Vizag")
    sophia.respond("what is recursion")

    assert sophia.brain.extracted == []


def test_usage_command_is_answered_locally(sophia):

    result = sophia.respond("usage")

    assert "requests" in result["response"] or "No AI" in result["response"]
    assert sophia.memory.get_history() == []


def test_long_history_is_compacted(sophia):

    for i in range(40):
        sophia.memory.add("user", f"m{i}")

    sophia.brain.replies.append(reply("ok"))
    sophia.respond("one more")

    assert sophia.summary.get() == "summary"
    assert len(sophia.memory.get_history()) <= 12
