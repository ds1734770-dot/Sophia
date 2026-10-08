"""
Sophia's tool set. Each tool wraps an existing manager and is given a
safety tier (see app.tools.registry.Risk).
"""

import re
from datetime import datetime

from app.brain.engines.calculator_engine import UnsafeExpression, safe_eval
from app.memory.profile_storage import ProfileStorage
from app.computer.shell_runner import ShellBlocked, classify
from app.file.path_guard import PathGuard
from app.tools.file_tools import register_file_tools
from app.tools.personal_tools import register_personal_tools
from app.tools.reminder_tools import register_reminder_tools
from app.tools.screen_tools import register_screen_tools
from app.tools.registry import Risk, Tool, ToolBlocked, ToolRegistry
from app.tools.web_tools import register_web_tools

STRING = {"type": "string"}

DATE_FORMAT = "%Y-%m-%d"
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def build_default_registry(
    computer,
    browser,
    files,
    search,
    planner,
    system=None,
    vision=None,
    shell=None,
    guard=None,
    audit=None,
    notes=None,
    web=None,
    personal=None,
    reminders=None,
    screen=None,
    undo=None,
    screen_policy=None,
):
    """
    Create the registry with every built-in tool.

    computer: ComputerManager   browser: BrowserManager
    files: FileManager          search: FileSearch
    planner: ScheduleManager    system: SystemControls (optional)
    vision: callable(question)  shell: ShellRunner (optional)
    guard: PathGuard            audit: callable for the action log
    """

    guard = guard or PathGuard()

    registry = ToolRegistry(audit=audit)

    # ----------------------------------------------
    # Information
    # ----------------------------------------------

    def get_current_time(context):

        return datetime.now().strftime("%A, %d %B %Y, %I:%M:%S %p")

    def calculate(context, expression):

        try:
            result = safe_eval(expression)

        except ZeroDivisionError:
            return False, "Division by zero."

        except (UnsafeExpression, SyntaxError, ValueError, OverflowError):
            return False, "That is not a plain arithmetic expression."

        return True, str(result)

    registry.register(Tool(
        name="get_current_time",
        description="Get the current local date and time.",
        handler=get_current_time,
    ))

    registry.register(Tool(
        name="calculate",
        description=(
            "Evaluate an arithmetic expression using numbers, "
            "+ - * / // % ** and parentheses."
        ),
        parameters={"expression": STRING},
        required=["expression"],
        handler=calculate,
    ))

    # ----------------------------------------------
    # Applications and folders
    # ----------------------------------------------

    registry.register(Tool(
        name="open_application",
        description=(
            "Open an installed Windows application by name, "
            "for example 'chrome', 'notepad' or 'visual studio code'."
        ),
        parameters={"name": STRING},
        required=["name"],
        handler=lambda context, name: computer.open_app(name),
    ))

    registry.register(Tool(
        name="close_application",
        description=(
            "Close a running application. By default it is asked to "
            "close politely (it may offer to save). Only set force=true "
            "if the user explicitly asks to force close it; unsaved "
            "work is then lost."
        ),
        parameters={
            "name": STRING,
            "force": {"type": "boolean"},
        },
        required=["name"],
        risk=Risk.CONFIRM,
        preview=lambda a: (
            f"I'm about to force-close {a['name']}. "
            "Unsaved work in it will be lost."
            if a.get("force")
            else f"I'm about to close {a['name']}."
        ),
        handler=lambda context, name, force=False: computer.close_app(
            name, force=bool(force)
        ),
    ))

    registry.register(Tool(
        name="window_action",
        description=(
            "Switch to, minimize, maximize or restore the open window "
            "whose title contains the given text."
        ),
        parameters={
            "name": STRING,
            "action": {
                "type": "string",
                "enum": ["focus", "minimize", "maximize", "restore"],
            },
        },
        required=["name", "action"],
        handler=lambda context, name, action: computer.window_action(
            name, action
        ),
    ))

    registry.register(Tool(
        name="open_folder",
        description=(
            "Open a well-known folder in File Explorer, "
            "such as downloads, documents or desktop."
        ),
        parameters={"name": STRING},
        required=["name"],
        handler=lambda context, name: computer.open_folder(name),
    ))

    registry.register(Tool(
        name="close_folder",
        description="Close an open File Explorer window for a known folder.",
        parameters={"name": STRING},
        required=["name"],
        handler=lambda context, name: computer.close_folder(name),
    ))

    registry.register(Tool(
        name="lock_computer",
        description="Lock the Windows session (the user signs back in).",
        handler=lambda context: computer.lock(),
    ))

    # ----------------------------------------------
    # Web
    # ----------------------------------------------

    def open_website(context, target):

        target = target.strip()

        if re.match(r"^https?://", target, re.IGNORECASE):
            return browser.open_url(target)

        success, response = browser.open_website(target.lower())

        if success:
            return True, response

        # "example.com" without a scheme
        if re.fullmatch(r"[\w-]+(\.[\w-]+)+(/\S*)?", target):
            return browser.open_url("https://" + target)

        return False, response

    def search_in_browser(context, query, site="google"):

        if site == "youtube":
            return browser.youtube_search(query)

        return browser.google_search(query)

    registry.register(Tool(
        name="open_website",
        description=(
            "Open a website in the browser. Accepts a known name "
            "(google, youtube, github, chatgpt, stackoverflow) or an "
            "http(s) URL or domain."
        ),
        parameters={"target": STRING},
        required=["target"],
        handler=open_website,
    ))

    registry.register(Tool(
        name="search_in_browser",
        description=(
            "Open a Google or YouTube search page in the user's browser "
            "so THEY can look at it. To find out something yourself, use "
            "web_search instead."
        ),
        parameters={
            "query": STRING,
            "site": {"type": "string", "enum": ["google", "youtube"]},
        },
        required=["query"],
        handler=search_in_browser,
    ))

    # ----------------------------------------------
    # Web (search, read pages, weather)
    # ----------------------------------------------

    register_web_tools(registry, **(web or {}))

    # ----------------------------------------------
    # Files
    # ----------------------------------------------

    register_file_tools(registry, files, search, guard, undo=undo)

    # ----------------------------------------------
    # System controls
    # ----------------------------------------------

    if system is not None:

        def set_volume(context, level=None, change=None, steps=5):

            if level is not None:
                return system.set_volume(level)

            if change in ("up", "down"):
                return system.change_volume(change, steps)

            if change == "mute":
                return system.toggle_mute()

            return False, "Give a level (0-100), or change = up, down or mute."

        registry.register(Tool(
            name="set_volume",
            description=(
                "Set the speaker volume to a level from 0 to 100, or "
                "change it: change = up / down (steps of about 2%) or "
                "mute (toggles mute)."
            ),
            parameters={
                "level": {"type": "integer"},
                "change": {"type": "string", "enum": ["up", "down", "mute"]},
                "steps": {"type": "integer"},
            },
            handler=set_volume,
        ))

        registry.register(Tool(
            name="set_brightness",
            description="Set the screen brightness (0-100). Laptop screens only.",
            parameters={"level": {"type": "integer"}},
            required=["level"],
            handler=lambda context, level: system.set_brightness(level),
        ))

        registry.register(Tool(
            name="take_screenshot",
            description="Save a screenshot of the screen to Pictures/Sophia.",
            handler=lambda context: system.screenshot(),
        ))

        registry.register(Tool(
            name="power_action",
            description=(
                "Shut down, restart or sleep the computer. Shutdown and "
                "restart start a 30 second countdown that can be "
                "cancelled with action=cancel."
            ),
            parameters={
                "action": {
                    "type": "string",
                    "enum": ["shutdown", "restart", "sleep", "cancel"],
                },
            },
            required=["action"],
            risk=Risk.DANGEROUS,
            preview=lambda a: (
                "I'm about to cancel the pending shutdown."
                if a["action"] == "cancel"
                else f"I'm about to {a['action']} your computer. "
                "Save your work first."
            ),
            handler=lambda context, action: system.power(action),
        ))

    if vision is not None:

        registry.register(Tool(
            name="look_at_screen",
            description=(
                "Look at the user's screen and answer a question about "
                "it, for example 'what error is showing?' or 'summarize "
                "this page'. Sends a screenshot to Gemini."
            ),
            parameters={"question": STRING},
            required=["question"],
            risk=Risk.CONFIRM,
            # By default she may look when a request needs it; the user
            # can switch on "ask first" in the menu.
            risk_fn=lambda a: (
                Risk.CONFIRM if (screen_policy or {}).get("confirm") else Risk.SAFE
            ),
            preview=lambda a: (
                "I'm about to take a screenshot of your screen and send "
                f"it to Gemini to answer: \"{a['question']}\""
            ),
            handler=lambda context, question: vision(question),
        ))

    # ----------------------------------------------
    # Memory (what Sophia knows about the user)
    # ----------------------------------------------

    def remember_fact(context, key, value):

        key = key.strip().lower().replace(" ", "_")

        context.profile.set(key, value)

        ProfileStorage.save(context.profile.get_all())

        return True, f"Remembered: {key} = {value}."

    def forget_fact(context, key):

        key = key.strip().lower().replace(" ", "_")

        facts = context.profile.get_all()

        if key not in facts:
            return False, f"I don't have anything stored as '{key}'."

        del facts[key]

        ProfileStorage.save(facts)

        return True, f"Forgot '{key}'."

    def list_memories(context):

        facts = context.profile.get_all()

        if not facts:
            return True, "I haven't stored any facts about you yet."

        return True, "\n".join(f"{k}: {v}" for k, v in facts.items())

    registry.register(Tool(
        name="remember_fact",
        description=(
            "Store a lasting fact about the user when they ask you to "
            "remember something. key is a short label like "
            "'favorite_food'."
        ),
        parameters={"key": STRING, "value": STRING},
        required=["key", "value"],
        handler=remember_fact,
    ))

    registry.register(Tool(
        name="forget_fact",
        description="Delete one stored fact about the user, by its key.",
        parameters={"key": STRING},
        required=["key"],
        risk=Risk.CONFIRM,
        preview=lambda a: f"I'm about to forget '{a['key']}'.",
        handler=forget_fact,
    ))

    registry.register(Tool(
        name="list_memories",
        description="List everything stored about the user.",
        handler=list_memories,
    ))

    # ----------------------------------------------
    # Notes, to-dos, system status, clipboard, media
    # ----------------------------------------------

    if notes is not None:
        register_personal_tools(
            registry, notes, browser, system=system, **(personal or {})
        )

    # ----------------------------------------------
    # Timers and routines
    # ----------------------------------------------

    if reminders is not None:
        register_reminder_tools(registry, *reminders)

    # ----------------------------------------------
    # Acting on the screen
    # ----------------------------------------------

    if screen is not None:
        register_screen_tools(registry, screen)

    # ----------------------------------------------
    # Shell
    # ----------------------------------------------

    if shell is not None:

        def shell_risk(args):

            try:
                level = classify(args["command"])

            except ShellBlocked as e:
                raise ToolBlocked(str(e))

            return Risk.DANGEROUS if level == "dangerous" else Risk.CONFIRM

        registry.register(Tool(
            name="run_powershell",
            description=(
                "Run a PowerShell command on the user's PC and return "
                "its output. Use it for things no other tool covers: "
                "system information, installed programs, network checks, "
                "processes, scripts. The user always sees the exact "
                "command and must confirm. Prefer the dedicated tools "
                "when one exists. Keep commands short and read-only "
                "unless the user asked for a change."
            ),
            parameters={
                "command": STRING,
                "timeout_seconds": {"type": "integer"},
            },
            required=["command"],
            risk=Risk.CONFIRM,
            risk_fn=shell_risk,
            trustable=False,
            preview=lambda a: (
                "I'm about to run this PowerShell command:\n\n"
                f"    {a['command']}"
            ),
            handler=lambda context, command, timeout_seconds=30: shell.run(
                command, timeout_seconds
            ),
        ))

    # ----------------------------------------------
    # Schedule
    # ----------------------------------------------

    def add_schedule(context, date, time, task):

        try:
            datetime.strptime(date, DATE_FORMAT)
        except ValueError:
            return False, "The date must look like 2026-10-08."

        if not TIME_PATTERN.match(time):
            return False, "The time must be 24-hour HH:MM, like 18:30."

        if any(
            item["time"] == time and item["task"] == task
            for item in planner.get_schedule(date)
        ):
            return True, "That entry already exists."

        planner.add_schedule(date, time, task)

        return True, f"Added '{task}' on {date} at {time}."

    def get_schedule(context, date):

        items = planner.get_schedule(date)

        if not items:
            return True, f"Nothing scheduled on {date}."

        return True, "\n".join(f"{i['time']} {i['task']}" for i in items)

    def clear_schedule(context, date):

        planner.delete_schedule(date)

        return True, f"Cleared everything scheduled on {date}."

    registry.register(Tool(
        name="add_schedule",
        description=(
            "Add a schedule entry. date is YYYY-MM-DD, time is 24-hour "
            "HH:MM. Work out the date from the current date given in "
            "the system instruction."
        ),
        parameters={"date": STRING, "time": STRING, "task": STRING},
        required=["date", "time", "task"],
        handler=add_schedule,
    ))

    registry.register(Tool(
        name="get_schedule",
        description="List the schedule entries for a date (YYYY-MM-DD).",
        parameters={"date": STRING},
        required=["date"],
        handler=get_schedule,
    ))

    registry.register(Tool(
        name="clear_schedule",
        description="Remove every schedule entry for a date (YYYY-MM-DD).",
        parameters={"date": STRING},
        required=["date"],
        risk=Risk.CONFIRM,
        preview=lambda a: f"I'm about to clear everything scheduled on {a['date']}.",
        handler=clear_schedule,
    ))

    return registry
