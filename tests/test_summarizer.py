from app.memory.memory import Memory
from app.memory.conversation_summary import ConversationSummary
from app.memory.summarizer import Summarizer


def filled(count):

    memory = Memory()

    for i in range(count):
        memory.add("user" if i % 2 == 0 else "assistant", f"m{i}")

    return memory


def test_short_history_is_untouched():

    memory, summary = filled(20), ConversationSummary()

    assert not Summarizer(lambda s, m: "x", trigger=30).maybe_summarize(memory, summary)
    assert len(memory.get_history()) == 20


def test_long_history_is_folded_into_the_summary():

    memory, summary = filled(40), ConversationSummary()
    summary.set("old summary")
    seen = {}

    def summarize(previous, messages):
        seen["previous"], seen["messages"] = previous, messages
        return "  new summary  "

    assert Summarizer(summarize, trigger=30, keep=10).maybe_summarize(memory, summary)

    assert summary.get() == "new summary"
    assert [m["content"] for m in memory.get_history()] == [f"m{i}" for i in range(30, 40)]
    assert seen["previous"] == "old summary"
    assert len(seen["messages"]) == 30


def test_failure_keeps_the_history():

    memory, summary = filled(40), ConversationSummary()

    def boom(previous, messages):
        raise RuntimeError("429")

    assert not Summarizer(boom).maybe_summarize(memory, summary)
    assert len(memory.get_history()) == 40
    assert summary.get() == ""


def test_empty_summary_is_rejected():

    memory, summary = filled(40), ConversationSummary()

    assert not Summarizer(lambda p, m: "   ").maybe_summarize(memory, summary)
    assert len(memory.get_history()) == 40
