import pytest

from app.brain.command_parser.command_parser import CommandParser

parser = CommandParser()


@pytest.mark.parametrize(
    "text, action, entity",
    [
        ("open chrome", "open", "chrome"),
        ("Open Chrome!", "open", "chrome"),
        ("launch spotify", "open", "spotify"),
        ("please open my downloads folder", "open", "downloads"),
        ("can you please open notepad?", "open", "notepad"),
        ("Hey Sophia, could you open vs code", "open", "vs code"),
        ("open scanner", "open", "scanner"),
        ("start chrome", "open", "chrome"),
        ("close notepad", "close", "notepad"),
        ("please quit spotify", "close", "spotify"),
        ("lock my pc", "lock", None),
        ("lock", "lock", ""),
        ("open music", "open", "spotify"),
    ],
)
def test_commands(text, action, entity):

    command = parser.parse(text)

    assert command.action == action

    if entity is not None:
        assert command.entity == entity


@pytest.mark.parametrize(
    "text",
    [
        "how do I run a python script",
        "I want to start learning DSA",
        "can you explain exit codes",
        "what can you do",
        "explain how to stop a process",
        "tell me when to open the window",
        "hello",
        "",
    ],
)
def test_conversation_is_not_a_command(text):

    assert parser.parse(text).action is None
