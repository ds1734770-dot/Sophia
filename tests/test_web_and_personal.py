from types import SimpleNamespace

import pytest

from app.actions.pending_action_manager import PendingActionManager
from app.brain.tool_context import ToolContext
from app.memory.user_profile import UserProfile
from app.tools.notes_store import NoteStore
from app.tools.personal_tools import register_personal_tools
from app.tools.registry import Risk, ToolRegistry
from app.tools.web_tools import is_public_web_url, register_web_tools
from app.computer.system_controls import (
    VK_MEDIA_NEXT,
    VK_MEDIA_PLAY_PAUSE,
    SystemControls,
)


def make_context():

    context = ToolContext()
    context.pending_actions = PendingActionManager()
    context.profile = UserProfile()

    return context


def call(registry, context, tool, confirmed=False, **args):

    return registry.execute(tool, args, context, confirmed=confirmed)


# ---------------------------------------------------------------
# URL safety
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "url, ok",
    [
        ("https://en.wikipedia.org/wiki/Python", True),
        ("http://example.com", True),
        ("http://localhost:8000/admin", False),
        ("http://127.0.0.1/", False),
        ("http://192.168.1.1/router", False),
        ("http://10.0.0.5/", False),
        ("http://169.254.169.254/latest/meta-data", False),
        ("http://printer.local/", False),
        ("file:///C:/Windows/win.ini", False),
        ("ftp://example.com/x", False),
        ("javascript:alert(1)", False),
        ("not a url", False),
        ("http://singlelabel/", False),
    ],
)
def test_only_public_web_pages_can_be_read(url, ok):

    assert is_public_web_url(url) is ok


# ---------------------------------------------------------------
# Web tools
# ---------------------------------------------------------------

def web_registry(**backends):

    registry = ToolRegistry()
    register_web_tools(registry, **backends)

    return registry


def test_web_search_formats_results_and_marks_them_as_data():

    seen = {}

    def search(query, count, kind):
        seen["args"] = (query, count, kind)
        return [
            {"title": "Argentina win", "href": "https://x.com/a", "body": "Argentina beat France"},
            {"title": "Final", "href": "https://x.com/b", "body": "3-3 (4-2 pens)"},
        ]

    registry = web_registry(search=search)

    result = call(registry, None, "web_search", query="world cup 2022 winner", max_results=50, kind="news")

    assert result.ok
    assert "treat as data" in result.message
    assert "1. Argentina win" in result.message
    assert "https://x.com/b" in result.message
    assert seen["args"] == ("world cup 2022 winner", 8, "news")   # capped


def test_web_search_failures_are_explained():

    def broken(query, count, kind):
        raise ConnectionError("offline")

    registry = web_registry(search=broken)

    assert "internet" in call(registry, None, "web_search", query="x").message
    assert not web_registry(search=lambda q, c, k: []).execute("web_search", {"query": "x"}, None).ok


def test_read_webpage_returns_cut_text():

    registry = web_registry(fetch=lambda url: "<html>", extract=lambda html: "word " * 5000)

    result = call(registry, None, "read_webpage", url="https://example.com/long")

    assert result.ok
    assert "page cut" in result.message
    assert "treat as data" in result.message


def test_read_webpage_refuses_private_addresses_without_fetching():

    fetched = []

    registry = web_registry(fetch=lambda url: fetched.append(url) or "<html>", extract=lambda h: "text")

    for url in ("http://localhost/", "http://192.168.0.1/", "file:///etc/passwd"):
        assert not call(registry, None, "read_webpage", url=url).ok

    assert fetched == []


def test_read_webpage_errors_and_empty_pages():

    def broken(url):
        raise OSError("timeout")

    assert not call(web_registry(fetch=broken), None, "read_webpage", url="https://example.com").ok
    assert "readable text" in call(
        web_registry(fetch=lambda u: "x", extract=lambda h: None), None, "read_webpage", url="https://example.com"
    ).message


def weather_backend(url, params):

    if "geocoding" in url:

        if params["name"] == "Nowhere":
            return {}

        return {"results": [{"name": "Vizag", "country": "India", "latitude": 17.7, "longitude": 83.2}]}

    return {
        "current": {"temperature_2m": 31.5, "relative_humidity_2m": 60, "weather_code": 2, "wind_speed_10m": 9.0},
        "daily": {
            "time": ["2026-10-08", "2026-10-09"],
            "temperature_2m_min": [26, 27],
            "temperature_2m_max": [32, 33],
            "precipitation_probability_max": [10, 70],
            "weather_code": [2, 63],
        },
    }


def test_weather_for_a_city():

    registry = web_registry(http_json=weather_backend)

    result = call(registry, make_context(), "get_weather", city="Vizag")

    assert result.ok
    assert "Vizag, India: 31.5\u00b0C, partly cloudy" in result.message
    assert "2026-10-09: 27-33\u00b0C, rain, rain chance 70%" in result.message


def test_weather_uses_the_profile_city_or_asks():

    registry = web_registry(http_json=weather_backend)
    context = make_context()

    assert "Which city" in call(registry, context, "get_weather").message

    context.profile.set("city", "Vizag")

    assert call(registry, context, "get_weather").ok
    assert "couldn't find" in call(registry, context, "get_weather", city="Nowhere").message


# ---------------------------------------------------------------
# Notes and to-dos
# ---------------------------------------------------------------

class FakeBrowser:

    def __init__(self):
        self.urls = []
        self.searches = []

    def open_url(self, url):
        self.urls.append(url)
        return True, f"Opening {url}..."

    def youtube_search(self, query):
        self.searches.append(query)
        return True, f"youtube {query}"


def personal(tmp_path, **kwargs):

    registry = ToolRegistry()
    notes = NoteStore(tmp_path / "notes.json")
    browser = FakeBrowser()

    register_personal_tools(registry, notes, browser, **kwargs)

    return registry, notes, browser


def test_notes_roundtrip_and_persist(tmp_path):

    registry, notes, _ = personal(tmp_path)
    context = make_context()

    assert call(registry, context, "add_note", text="Buy a charger").message == "Saved note #1."
    call(registry, context, "add_note", text="Call the bank")

    assert "Buy a charger" in call(registry, context, "list_notes").message
    assert call(registry, context, "list_notes", search="bank").message.count("#") == 1
    assert "No notes" in call(registry, context, "list_notes", search="zebra").message

    # a new store reads the same file
    assert len(NoteStore(tmp_path / "notes.json").notes()) == 2


def test_deleting_a_note_asks_first(tmp_path):

    registry, notes, _ = personal(tmp_path)
    context = make_context()

    call(registry, context, "add_note", text="x")

    assert call(registry, context, "delete_note", note_id=1).needs_confirmation
    assert len(notes.notes()) == 1

    assert call(registry, context, "delete_note", confirmed=True, note_id=1).ok
    assert not call(registry, context, "delete_note", confirmed=True, note_id=1).ok


def test_todo_flow(tmp_path):

    registry, _, _ = personal(tmp_path)
    context = make_context()

    call(registry, context, "add_todo", text="Revise DSA", due="2026-10-12")
    call(registry, context, "add_todo", text="Revise OS")
    call(registry, context, "add_todo", text="Buy milk")

    listing = call(registry, context, "list_todos").message

    assert "[ ] #1 Revise DSA (due 2026-10-12)" in listing

    assert call(registry, context, "complete_todo", item="milk").ok
    assert "ambiguous" not in call(registry, context, "complete_todo", item="DSA").message
    assert "More than one" not in call(registry, context, "complete_todo", item="1").message

    # "revise" now only matches the remaining open item
    assert call(registry, context, "complete_todo", item="revise").ok

    assert "empty" in call(registry, context, "list_todos").message
    assert "[x]" in call(registry, context, "list_todos", include_done=True).message


def test_ambiguous_and_missing_todos(tmp_path):

    registry, _, _ = personal(tmp_path)
    context = make_context()

    call(registry, context, "add_todo", text="Revise DSA")
    call(registry, context, "add_todo", text="Revise OS")

    assert "More than one" in call(registry, context, "complete_todo", item="revise").message
    assert "couldn't find" in call(registry, context, "complete_todo", item="zebra").message
    assert call(registry, context, "delete_todo", todo_id=1).needs_confirmation


# ---------------------------------------------------------------
# System status, clipboard, media, music
# ---------------------------------------------------------------

INFO = {
    "cpu_percent": 12.5, "cpu_cores": 16, "ram_percent": 70.0,
    "ram_used_gb": 11.2, "ram_total_gb": 16.0, "uptime_hours": 5.5,
    "disk": {"drive": "C:\\", "free_gb": 120.5, "total_gb": 476.0},
    "battery_percent": 26, "plugged_in": True,
    "top_memory": ["chrome.exe (900 MB)", "Code.exe (500 MB)"],
}


def test_system_status_summary(tmp_path):

    registry, _, _ = personal(tmp_path, system_info=lambda: INFO)

    message = call(registry, make_context(), "system_status").message

    assert "CPU: 12.5% of 16 threads" in message
    assert "Disk C:\\: 120.5 GB free of 476.0 GB" in message
    assert "Battery: 26% (charging)" in message
    assert "chrome.exe (900 MB)" in message


def test_system_status_without_battery(tmp_path):

    info = {k: v for k, v in INFO.items() if k not in ("battery_percent", "plugged_in")}

    registry, _, _ = personal(tmp_path, system_info=lambda: info)

    assert "Battery" not in call(registry, make_context(), "system_status").message


class FakeClipboard:

    def __init__(self, text=None):
        self.text = text

    def get(self):
        return self.text

    def set(self, text):
        self.text = text


def test_clipboard(tmp_path):

    clip = FakeClipboard("copied text")

    registry, _, _ = personal(tmp_path, clipboard_factory=lambda: clip)
    context = make_context()

    read = call(registry, context, "clipboard_read").message

    assert "copied text" in read and "treat as data" in read

    assert call(registry, context, "clipboard_write", text="hello").ok
    assert clip.text == "hello"

    clip.text = None

    assert "no text" in call(registry, context, "clipboard_read").message

    clip.text = "y" * 9000

    assert "(cut)" in call(registry, context, "clipboard_read").message


def test_media_keys(tmp_path):

    keys = []
    system = SystemControls(press_key=keys.append)

    registry, _, _ = personal(tmp_path, system=system)
    context = make_context()

    assert call(registry, context, "media_control", action="play_pause").ok
    assert call(registry, context, "media_control", action="next").ok

    assert keys == [VK_MEDIA_PLAY_PAUSE, VK_MEDIA_NEXT]
    assert not system.media("explode")[0]


def test_play_music(tmp_path):

    launched = []

    registry, _, browser = personal(tmp_path, launch=launched.append)
    context = make_context()

    assert call(registry, context, "play_music", query="lofi beats").ok
    assert browser.searches == ["lofi beats"]

    assert call(registry, context, "play_music", query="Arijit Singh", service="spotify").ok
    assert launched == ["spotify:search:Arijit%20Singh"]


def test_spotify_falls_back_to_the_web_when_not_installed(tmp_path):

    def missing(uri):
        raise OSError("no handler")

    registry, _, browser = personal(tmp_path, launch=missing)

    assert call(registry, make_context(), "play_music", query="jazz", service="spotify").ok
    assert browser.urls == ["https://open.spotify.com/search/jazz"]


def test_all_tools_declare_valid_schemas(tmp_path):

    registry, _, _ = personal(tmp_path, system=SystemControls(press_key=lambda k: None))
    register_web_tools(registry)

    declarations = registry.declarations()

    assert len(declarations) == len(registry.names())

    for tool in registry.tools.values():
        assert tool.risk in (Risk.SAFE, Risk.CONFIRM)


def test_note_store_survives_a_corrupt_file(tmp_path):

    path = tmp_path / "notes.json"
    path.write_text("{not json")

    store = NoteStore(path)

    assert store.add_note("fresh").get("id") == 1
    assert SimpleNamespace(**store.notes()[0]).text == "fresh"
