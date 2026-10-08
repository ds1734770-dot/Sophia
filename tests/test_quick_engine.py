import pytest

from app.brain.engines.quick_engine import QuickEngine
from app.brain.tool_context import ToolContext
from app.tools.registry import Tool, ToolRegistry

engine = QuickEngine()


@pytest.mark.parametrize("text,expected", [
    ("volume to 30", ("set_volume", {"level": 30})),
    ("Set the volume to 45%", ("set_volume", {"level": 45})),
    ("volume up", ("set_volume", {"change": "up"})),
    ("louder", ("set_volume", {"change": "up"})),
    ("mute", ("set_volume", {"change": "mute"})),
    ("Hey Sophia, please pause the music", ("media_control", {"action": "play_pause"})),
    ("next song", ("media_control", {"action": "next"})),
    ("stop", ("media_control", {"action": "stop"})),
    ("set a timer for 10 minutes", ("set_timer", {"minutes": 10})),
    ("timer for 30 seconds", ("set_timer", {"minutes": 0.5})),
    ("set a 5 minute timer", ("set_timer", {"minutes": 5})),
    ("take a screenshot", ("take_screenshot", {})),
    ("battery", ("system_status", {})),
    ("am I online?", ("network_status", {})),
    ("weather", ("get_weather", {})),
    ("what's the weather in Vizag", ("get_weather", {"city": "vizag"})),
    ("news about cricket", ("news_headlines", {"topic": "cricket"})),
    ("define serendipity", ("define_word", {"word": "serendipity"})),
    ("what does ephemeral mean?", ("define_word", {"word": "ephemeral"})),
    ("generate a password", ("generate_password", {})),
    ("switch to dark mode", ("set_windows_theme", {"mode": "dark"})),
    ("show my todos", ("list_todos", {})),
    ("convert 5 miles to km", ("convert_units", {"value": 5.0, "from_unit": "miles", "to_unit": "km"})),
    ("100 usd to inr", ("convert_currency", {"amount": 100.0, "from_currency": "usd", "to_currency": "inr"})),
    ("90 min to hr", ("convert_units", {"value": 90.0, "from_unit": "min", "to_unit": "hr"})),
])
def test_quick_commands_are_matched(text, expected):

    assert engine.match(text) == expected


@pytest.mark.parametrize("text", [
    "what does it do when I click volume",
    "explain how a timer works",
    "play some lofi on youtube",
    "volume of a sphere with radius 3",
    "what does the news mean for the market",
    "remind me to call mom in 10 minutes",
    "pause",   # handled, see below: this one IS quick
][:-1])
def test_open_ended_requests_go_to_gemini(text):

    assert engine.match(text) is None


def make_context(ran):

    registry = ToolRegistry()

    for name in ("set_volume", "convert_units", "define_word"):
        registry.register(Tool(
            name=name, description=name,
            parameters={"level": {"type": "integer"}, "change": {"type": "string"},
                        "value": {"type": "number"}, "from_unit": {"type": "string"},
                        "to_unit": {"type": "string"}, "word": {"type": "string"}},
            handler=lambda context, _n=name, **a: ran.append((_n, a)) or ((False, "no") if _n != "set_volume" else (True, "Volume 30%")),
        ))

    context = ToolContext()
    context.registry = registry

    return context


def test_a_quick_command_runs_the_tool_without_gemini():

    ran = []

    result = engine.execute("volume to 30", make_context(ran))

    assert result == {"handled": True, "response": "Volume 30%"}
    assert ran == [("set_volume", {"level": 30})]


def test_a_failed_lookup_falls_through_to_gemini():

    result = engine.execute("5 apples to pears", make_context([]))

    assert result["handled"] is False


def test_missing_tool_or_registry_is_not_handled():

    assert engine.execute("volume to 30", ToolContext())["handled"] is False

    context = ToolContext()
    context.registry = ToolRegistry()

    assert engine.execute("volume to 30", context)["handled"] is False
