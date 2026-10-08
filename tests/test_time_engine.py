import pytest

from app.brain.engines.time_engine import TimeEngine

engine = TimeEngine()


@pytest.mark.parametrize(
    "text",
    [
        "time",
        "what time is it",
        "What time is it?",
        "what's the time",
        "what is the current time",
        "tell me the time",
        "current time",
        "hey sophia what time is it",
    ],
)
def test_time_questions(text):

    result = engine.execute(text, None)

    assert result["handled"]
    assert ":" in result["response"]


@pytest.mark.parametrize(
    "text",
    [
        "what is today's date",
        "what day is it",
        "date",
    ],
)
def test_date_questions(text):

    assert engine.execute(text, None)["handled"]


@pytest.mark.parametrize(
    "text",
    [
        "explain time complexity of quicksort",
        "explain time complexity of binary search",
        "sometimes I feel lost",
        "my favorite pastime is chess",
        "what is the time complexity of merge sort",
        "update the date format in my code",
    ],
)
def test_other_sentences_are_not_hijacked(text):

    assert not engine.execute(text, None)["handled"]
