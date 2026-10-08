"""
Tools for timers and recurring routines.
"""

import re
from datetime import datetime, timedelta

from app.planner.reminder_service import DAY_NAMES, parse_days
from app.tools.registry import Risk, Tool

STRING = {"type": "string"}

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

MAX_TIMER_MINUTES = 24 * 60


def describe_days(days):

    if sorted(days) == list(range(7)):
        return "every day"

    if sorted(days) == [0, 1, 2, 3, 4]:
        return "weekdays"

    if sorted(days) == [5, 6]:
        return "weekends"

    return ", ".join(DAY_NAMES[d] for d in sorted(days))


def register_reminder_tools(registry, timers, routines, clock=datetime.now):

    # ----------------------------------------------
    # Timers
    # ----------------------------------------------

    def set_timer(context, minutes, label="Timer"):

        minutes = float(minutes)

        if not 0 < minutes <= MAX_TIMER_MINUTES:
            return False, "A timer can be between a moment and 24 hours."

        due = clock() + timedelta(minutes=minutes)

        timer = timers.add(due, label)

        return True, (
            f"Timer #{timer['id']} set for {minutes:g} minute(s): "
            f"'{label}' at {due:%H:%M:%S}."
        )

    def list_timers(context):

        if not timers.data:
            return True, "No timers running."

        now = clock()

        lines = []

        for t in timers.data:

            left = datetime.fromisoformat(t["due"]) - now

            lines.append(
                f"#{t['id']} {t['label']}: "
                f"{max(0, int(left.total_seconds() // 60))} min left"
            )

        return True, "\n".join(lines)

    def cancel_timer(context, timer_id):

        if timers.cancel(int(timer_id)):
            return True, f"Cancelled timer #{timer_id}."

        return False, f"There is no timer #{timer_id}."

    registry.register(Tool(
        name="set_timer",
        description=(
            "Start a countdown timer. Sophia alerts the user (pop-up and "
            "voice) when it ends. minutes may be fractional."
        ),
        parameters={"minutes": {"type": "number"}, "label": STRING},
        required=["minutes"],
        handler=set_timer,
    ))

    registry.register(Tool(
        name="list_timers",
        description="Show running timers and the time left on each.",
        handler=list_timers,
    ))

    registry.register(Tool(
        name="cancel_timer",
        description="Cancel a timer by its number.",
        parameters={"timer_id": {"type": "integer"}},
        required=["timer_id"],
        handler=cancel_timer,
    ))

    # ----------------------------------------------
    # Routines
    # ----------------------------------------------

    def add_routine(context, name, time, text, days="daily", kind="reminder"):

        if not TIME_PATTERN.match(time):
            return False, "The time must be 24-hour HH:MM, like 08:00."

        parsed = parse_days(days)

        if parsed is None:
            return False, "days must be daily, weekdays, weekends, or names like mon,wed,fri."

        if kind not in ("reminder", "prompt"):
            return False, "kind must be 'reminder' or 'prompt'."

        routine = routines.add(name, time, parsed, kind, text)

        what = "alert you with" if kind == "reminder" else "run this request and show you the answer:"

        return True, (
            f"Routine #{routine['id']} '{name}' will {what} \"{text}\" "
            f"at {time}, {describe_days(parsed)}."
        )

    def list_routines(context):

        if not routines.data:
            return True, "No routines set up."

        return True, "\n".join(
            f"#{r['id']} {r['name']} - {r['time']}, {describe_days(r['days'])} ({r['kind']}): {r['text']}"
            for r in routines.data
        )

    def remove_routine(context, routine_id):

        if routines.remove(int(routine_id)):
            return True, f"Removed routine #{routine_id}."

        return False, f"There is no routine #{routine_id}."

    registry.register(Tool(
        name="add_routine",
        description=(
            "Create a recurring routine. kind='reminder' alerts the user "
            "with the text at the given time (for example 'drink water'). "
            "kind='prompt' makes Sophia carry out the text as a request at "
            "that time and show the answer (for example a morning briefing: "
            "'Give me a morning briefing with today's weather in my city, "
            "my schedule and my open to-dos'). Prompt routines can only use "
            "read-only tools. time is 24-hour HH:MM; days is daily, "
            "weekdays, weekends or e.g. mon,wed,fri."
        ),
        parameters={
            "name": STRING,
            "time": STRING,
            "text": STRING,
            "days": STRING,
            "kind": {"type": "string", "enum": ["reminder", "prompt"]},
        },
        required=["name", "time", "text"],
        handler=add_routine,
    ))

    registry.register(Tool(
        name="list_routines",
        description="List the recurring routines.",
        handler=list_routines,
    ))

    registry.register(Tool(
        name="remove_routine",
        description="Delete a routine by its number.",
        parameters={"routine_id": {"type": "integer"}},
        required=["routine_id"],
        risk=Risk.CONFIRM,
        preview=lambda a: f"I'm about to remove routine #{a['routine_id']}.",
        handler=remove_routine,
    ))
