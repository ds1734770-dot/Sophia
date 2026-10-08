import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import time
from datetime import datetime, timedelta

import pytest

from app.actions.pending_action_manager import PendingActionManager
from app.brain.tool_context import ToolContext
from app.planner.reminder_service import (
    FiredStore,
    ReminderService,
    RoutineStore,
    TimerStore,
    parse_days,
)
from app.tools.reminder_tools import register_reminder_tools
from app.tools.registry import Risk, Tool, ToolRegistry

NOW = datetime(2026, 10, 8, 9, 30, 0)   # a Thursday


class FakePlanner:

    def __init__(self, items=None):
        self.items = items or {}

    def get_schedule(self, date):
        return self.items.get(date, [])


def make_service(tmp_path, planner=None, run_prompt=None):

    alerts = []

    service = ReminderService(
        planner=planner or FakePlanner(),
        timers=TimerStore(tmp_path / "timers.json"),
        routines=RoutineStore(tmp_path / "routines.json"),
        fired=FiredStore(tmp_path / "fired.json"),
        notify=lambda title, text: alerts.append((title, text)),
        run_prompt=run_prompt,
        interval=0.01,
    )

    return service, alerts


# ---------------------------------------------------------------
# Day parsing
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("daily", [0, 1, 2, 3, 4, 5, 6]),
        (None, [0, 1, 2, 3, 4, 5, 6]),
        ("weekdays", [0, 1, 2, 3, 4]),
        ("weekends", [5, 6]),
        ("mon,wed,fri", [0, 2, 4]),
        ("Monday, friday", [0, 4]),
        ("someday", None),
        ("mon,xyz", None),
    ],
)
def test_parse_days(text, expected):

    assert parse_days(text) == expected


# ---------------------------------------------------------------
# Agenda reminders
# ---------------------------------------------------------------

def test_due_agenda_entries_alert_once(tmp_path):

    planner = FakePlanner({"2026-10-08": [
        {"time": "09:00", "task": "Stand-up"},
        {"time": "18:00", "task": "Gym"},
    ]})

    service, alerts = make_service(tmp_path, planner)

    assert service.tick(NOW) == 1
    assert alerts == [("Reminder", "09:00 Stand-up")]

    # not again, and 18:00 is still in the future
    assert service.tick(NOW + timedelta(minutes=5)) == 0
    assert len(alerts) == 1

    assert service.tick(NOW.replace(hour=18, minute=1)) == 1
    assert alerts[-1] == ("Reminder", "18:00 Gym")


def test_old_entries_are_skipped_silently_after_downtime(tmp_path):

    planner = FakePlanner({"2026-10-08": [{"time": "06:00", "task": "Wake up"}]})

    service, alerts = make_service(tmp_path, planner)

    assert service.tick(NOW) == 0
    assert alerts == []

    # and it is remembered, so it never fires later either
    assert service.tick(NOW + timedelta(hours=1)) == 0


def test_fired_entries_survive_a_restart(tmp_path):

    planner = FakePlanner({"2026-10-08": [{"time": "09:15", "task": "Call"}]})

    service, alerts = make_service(tmp_path, planner)
    service.tick(NOW)

    again, alerts2 = make_service(tmp_path, planner)
    again.tick(NOW)

    assert len(alerts) == 1 and alerts2 == []


# ---------------------------------------------------------------
# Timers
# ---------------------------------------------------------------

def test_timers_fire_once_and_disappear(tmp_path):

    service, alerts = make_service(tmp_path)

    service.timers.add(NOW + timedelta(minutes=10), "Tea")

    assert service.tick(NOW) == 0

    assert service.tick(NOW + timedelta(minutes=11)) == 1
    assert alerts == [("Timer", "Time's up: Tea")]
    assert service.timers.data == []

    assert service.tick(NOW + timedelta(minutes=12)) == 0


def test_timers_survive_a_restart(tmp_path):

    service, _ = make_service(tmp_path)
    service.timers.add(NOW + timedelta(minutes=10), "Laundry")

    again, alerts = make_service(tmp_path)

    assert again.tick(NOW + timedelta(minutes=10)) == 1
    assert alerts[0][1].endswith("Laundry")


# ---------------------------------------------------------------
# Routines
# ---------------------------------------------------------------

def test_reminder_routine_fires_once_a_day(tmp_path):

    service, alerts = make_service(tmp_path)

    service.routines.add("Water", "09:00", list(range(7)), "reminder", "Drink water")

    assert service.tick(NOW) == 1
    assert alerts == [("Water", "Drink water")]

    assert service.tick(NOW + timedelta(minutes=30)) == 0

    # next day it fires again
    assert service.tick(NOW + timedelta(days=1)) == 1


def test_routine_waits_for_its_time_and_its_days(tmp_path):

    service, alerts = make_service(tmp_path)

    service.routines.add("Later", "18:00", list(range(7)), "reminder", "x")
    service.routines.add("Weekend", "08:00", [5, 6], "reminder", "y")

    assert service.tick(NOW) == 0
    assert alerts == []


def test_missed_routines_are_skipped_not_fired_late(tmp_path):

    service, alerts = make_service(tmp_path)

    service.routines.add("Briefing", "05:00", list(range(7)), "reminder", "x")

    assert service.tick(NOW) == 0
    assert service.tick(NOW + timedelta(minutes=1)) == 0
    assert alerts == []


def test_prompt_routine_shows_the_answer(tmp_path):

    asked = []

    service, alerts = make_service(
        tmp_path, run_prompt=lambda text: asked.append(text) or "Sunny, 32C. Two to-dos."
    )

    service.routines.add("Morning briefing", "08:00", list(range(7)), "prompt", "Give me a briefing")

    assert service.tick(NOW) == 1
    assert asked == ["Give me a briefing"]
    assert alerts == [("Morning briefing", "Sunny, 32C. Two to-dos.")]


def test_failed_prompt_routine_does_not_alert_or_repeat(tmp_path):

    def broken(text):
        raise RuntimeError("quota")

    service, alerts = make_service(tmp_path, run_prompt=broken)

    service.routines.add("Briefing", "08:00", list(range(7)), "prompt", "x")

    assert service.tick(NOW) == 0
    assert alerts == []

    # it will try again tomorrow, not every 15 seconds
    assert service.tick(NOW + timedelta(minutes=1)) == 0


def test_background_loop_runs_and_survives_errors(tmp_path):

    service, alerts = make_service(tmp_path)

    calls = []

    def flaky(now):
        calls.append(now)
        if len(calls) == 1:
            raise RuntimeError("boom")

    service.tick = flaky

    service.start()
    service.start()

    deadline = time.time() + 2

    while len(calls) < 3 and time.time() < deadline:
        time.sleep(0.01)

    service.stop()

    assert len(calls) >= 3


# ---------------------------------------------------------------
# Tools
# ---------------------------------------------------------------

@pytest.fixture
def tools(tmp_path):

    registry = ToolRegistry()
    timers = TimerStore(tmp_path / "timers.json")
    routines = RoutineStore(tmp_path / "routines.json")

    register_reminder_tools(registry, timers, routines, clock=lambda: NOW)

    context = ToolContext()
    context.pending_actions = PendingActionManager()

    def call(tool_name, confirmed=False, **args):
        return registry.execute(tool_name, args, context, confirmed=confirmed)

    return call, timers, routines


def test_timer_tools(tools):

    call, timers, _ = tools

    result = call("set_timer", minutes=25, label="Pomodoro")

    assert result.ok and "09:55:00" in result.message
    assert "25 min left" in call("list_timers").message
    assert call("cancel_timer", timer_id=1).ok
    assert "No timers" in call("list_timers").message
    assert not call("cancel_timer", timer_id=1).ok


def test_timer_limits(tools):

    call, _, _ = tools

    assert not call("set_timer", minutes=0).ok
    assert not call("set_timer", minutes=100000).ok
    assert call("set_timer", minutes=0.5).ok


def test_routine_tools_validate_input(tools):

    call, _, routines = tools

    assert not call("add_routine", name="x", time="8am", text="x").ok
    assert not call("add_routine", name="x", time="08:00", text="x", days="whenever").ok
    assert not call("add_routine", name="x", time="08:00", text="x", kind="shell").ok
    assert routines.data == []

    ok = call("add_routine", name="Briefing", time="08:00", text="Weather and todos", days="weekdays", kind="prompt")

    assert ok.ok
    assert "weekdays" in ok.message
    assert routines.data[0]["days"] == [0, 1, 2, 3, 4]
    assert "Briefing - 08:00" in call("list_routines").message


def test_removing_a_routine_asks_first(tools):

    call, _, routines = tools

    call("add_routine", name="Water", time="10:00", text="Drink")

    assert call("remove_routine", routine_id=1).needs_confirmation
    assert len(routines.data) == 1

    assert call("remove_routine", confirmed=True, routine_id=1).ok
    assert not call("remove_routine", confirmed=True, routine_id=1).ok


def test_safe_only_view_for_background_work():

    registry = ToolRegistry()
    registry.register(Tool(name="read", description="x", handler=lambda c: "ok"))
    registry.register(Tool(name="change", description="x", handler=lambda c: "ok", risk=Risk.CONFIRM))
    registry.register(Tool(name="shell", description="x", handler=lambda c: "ok", risk_fn=lambda a: Risk.SAFE))

    assert registry.safe_only().names() == ["read"]


# ---------------------------------------------------------------
# The window shows alerts
# ---------------------------------------------------------------

def test_the_window_shows_and_speaks_alerts():

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow
    from app.ui.widgets import Bubble
    from tests.test_ui import FakeAutostart, FakeSophia, FakeSpeaker, pump

    qapp = QApplication.instance() or QApplication([])

    class Notifying(FakeSophia):

        notifier = None

        def set_notifier(self, notifier):
            self.notifier = notifier

    sophia = Notifying()
    speaker = FakeSpeaker()

    window = MainWindow(
        lambda: sophia,
        speaker=speaker,
        settings=QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat),
        use_tray=False,
        autostart=FakeAutostart(),
    )

    assert pump(qapp, lambda: window.sophia is not None)

    window.voice_toggle.setChecked(True)

    # called from another thread, like the real service
    import threading
    threading.Thread(target=sophia.notifier, args=("Timer", "Time's up: Tea")).start()

    assert pump(qapp, lambda: any(
        "Time's up: Tea" in b.text() for b in window.chat.widget().findChildren(Bubble)
    ))
    assert speaker.said == ["Timer. Time's up: Tea"]
