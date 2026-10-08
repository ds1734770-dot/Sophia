from app.brain.engines.computer_engine import ComputerEngine
from app.computer.builtin_apps import merge_builtin
from app.computer.search.application_ranker import ApplicationRanker
from app.computer.search.confidence_evaluator import ConfidenceEvaluator
from app.computer.semantic.semantic_index import SemanticIndex
from app.memory.memory_storage import MemoryStorage

DISCOVERED = [
    {"name": "OneNote", "aliases": ["onenote"], "exe": "x", "type": "registry"},
    {"name": "Git Release Notes", "aliases": ["git release notes"], "exe": "y", "type": "registry"},
]


def best(query):

    ranker = ApplicationRanker()
    apps = SemanticIndex().build(merge_builtin(DISCOVERED))
    matches = ranker.rank(apps, query)

    return matches, ConfidenceEvaluator().confident(matches)


def test_notepad_and_calculator_are_found():

    for query, name in [("notepad", "Notepad"), ("calc", "Calculator"), ("calculator", "Calculator")]:

        matches, confident = best(query)

        assert matches[0].app["name"] == name
        assert confident


def test_builtin_does_not_duplicate_discovered_app():

    apps = merge_builtin([{"name": "Notepad", "aliases": [], "exe": "z", "type": "registry"}])

    assert [a["name"] for a in apps].count("Notepad") == 1


def test_saved_history_is_bounded(tmp_path, monkeypatch):

    monkeypatch.setattr(MemoryStorage, "FILE_NAME", tmp_path / "m.json")

    history = [{"role": "user", "content": str(i)} for i in range(500)]

    MemoryStorage.save(history)

    saved = MemoryStorage.load()

    assert len(saved) == MemoryStorage.MAX_SAVED
    assert saved[-1]["content"] == "499"


class FakeComputer:

    def __init__(self, app_result, folder_result=(False, "no folder")):
        self.app_result = app_result
        self.folder_result = folder_result

    def open_app(self, name):
        return self.app_result

    def open_folder(self, name):
        return self.folder_result

    def close_app(self, name):
        return False, "not running"

    def close_folder(self, name):
        return False, "not open"


def engine_with(computer):

    engine = ComputerEngine()
    engine.computer = computer

    return engine


def test_suggestions_are_not_lost():

    engine = engine_with(FakeComputer(
        (False, "I couldn't confidently identify the application.\n\nDid you mean:\n\n1. A")
    ))

    result = engine.execute("open edg", None)

    assert result["handled"]
    assert "Did you mean" in result["response"]


def test_unknown_short_app_gets_not_found_message():

    result = engine_with(FakeComputer((False, "No matching application found."))).execute("open zzzz", None)

    assert result["handled"]
    assert "zzzz" in result["response"]


def test_long_unknown_target_falls_through_to_chat():

    result = engine_with(FakeComputer((False, "No matching application found."))).execute(
        "run the quarterly sales analysis report for my team please", None
    )

    assert not result["handled"]


def test_open_without_target_asks():

    result = engine_with(FakeComputer((False, ""))).execute("open", None)

    assert result["handled"]
    assert "What" in result["response"]
