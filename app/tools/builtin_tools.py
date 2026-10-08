"""
Sophia's tool set. Each tool wraps an existing manager and is given a
safety tier (see app.tools.registry.Risk).
"""

import os
import re
from datetime import datetime
from pathlib import Path

from app.brain.engines.calculator_engine import UnsafeExpression, safe_eval
from app.file.path_guard import (
    EXECUTABLE_EXTENSIONS,
    allowed_roots,
    is_safe_name,
    resolve_allowed,
)
from app.tools.registry import Risk, Tool, ToolRegistry

STRING = {"type": "string"}

DATE_FORMAT = "%Y-%m-%d"
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def build_default_registry(computer, browser, files, indexer, planner):
    """
    Create the registry with every built-in tool.

    computer: ComputerManager   browser: BrowserManager
    files: FileManager          indexer: FileIndexer
    planner: ScheduleManager
    """

    registry = ToolRegistry()

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
            "Force-close a running application. Unsaved work in it "
            "is lost, so the user must confirm."
        ),
        parameters={"name": STRING},
        required=["name"],
        risk=Risk.CONFIRM,
        preview=lambda a: (
            f"I'm about to force-close {a['name']}. "
            "Unsaved work in it will be lost."
        ),
        handler=lambda context, name: computer.close_app(name),
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

    def web_search(context, query, site="google"):

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
        name="web_search",
        description="Open a Google or YouTube search in the browser.",
        parameters={
            "query": STRING,
            "site": {"type": "string", "enum": ["google", "youtube"]},
        },
        required=["query"],
        handler=web_search,
    ))

    # ----------------------------------------------
    # Files (limited to Desktop, Documents and Downloads)
    # ----------------------------------------------

    def find_files(context, query):

        success, results = indexer.search(query)

        if not success:
            return False, results

        lines = [
            f"{item['type']}: {item['path']}"
            for item in results[:10]
        ]

        return True, "\n".join(lines)

    def create_folder(context, name, location=None):

        if not is_safe_name(name):
            return False, "Folder names cannot contain slashes or colons."

        parent = None

        if location:

            # "Desktop", "documents" ... mean the folders in the home dir
            named = {r.name.lower(): r for r in allowed_roots()}

            if location.strip().lower() in named:
                location = named[location.strip().lower()]

            # Resolve a child path so the location itself may be one of
            # the allowed folders.
            parent = resolve_allowed(Path(location) / "_")

            if parent is None:
                return False, (
                    "I can only create folders inside Desktop, "
                    "Documents or Downloads."
                )

            parent = parent.parent

        success, response = files.create_folder(name, parent)

        if success:
            indexer.save()

        return success, response

    def rename_file(context, path, new_name):

        source = resolve_allowed(path)

        if source is None or not source.exists():
            return False, "I can only rename existing items inside Desktop, Documents or Downloads."

        if not is_safe_name(new_name):
            return False, "The new name cannot contain slashes or colons."

        if (source.parent / new_name).exists():
            return False, f"'{new_name}' already exists there."

        success, response = files.rename(source, new_name)

        if success:
            indexer.save()

        return success, response

    def delete_file(context, path):

        target = resolve_allowed(path)

        if target is None or not target.exists():
            return False, "I can only delete existing items inside Desktop, Documents or Downloads."

        success, response = files.delete(target)

        if success:
            indexer.save()

        return success, response

    def open_file(context, path):

        target = resolve_allowed(path)

        if target is None or not target.is_file():
            return False, "I can only open existing files inside Desktop, Documents or Downloads."

        if target.suffix.lower() in EXECUTABLE_EXTENSIONS:
            return False, "I won't open programs or scripts. Open those yourself."

        return files.open_file(target)

    registry.register(Tool(
        name="find_files",
        description=(
            "Search file and folder names in Desktop, Documents and "
            "Downloads. Returns full paths."
        ),
        parameters={"query": STRING},
        required=["query"],
        handler=find_files,
    ))

    registry.register(Tool(
        name="create_folder",
        description=(
            "Create a folder. Defaults to Documents; 'location' must be "
            "inside Desktop, Documents or Downloads."
        ),
        parameters={"name": STRING, "location": STRING},
        required=["name"],
        handler=create_folder,
    ))

    registry.register(Tool(
        name="open_file",
        description=(
            "Open a document, image or other non-program file with its "
            "default app. Needs the full path from find_files."
        ),
        parameters={"path": STRING},
        required=["path"],
        risk=Risk.CONFIRM,
        preview=lambda a: f"I'm about to open {a['path']}.",
        handler=open_file,
    ))

    registry.register(Tool(
        name="rename_file",
        description=(
            "Rename a file or folder. Needs the full path from "
            "find_files and just the new name."
        ),
        parameters={"path": STRING, "new_name": STRING},
        required=["path", "new_name"],
        risk=Risk.CONFIRM,
        preview=lambda a: f"I'm about to rename {a['path']} to '{a['new_name']}'.",
        handler=rename_file,
    ))

    registry.register(Tool(
        name="delete_file",
        description=(
            "Move a file or folder to the Recycle Bin. Needs the full "
            "path from find_files."
        ),
        parameters={"path": STRING},
        required=["path"],
        risk=Risk.DANGEROUS,
        preview=lambda a: (
            f"I'm about to move {a['path']} to the Recycle Bin."
        ),
        handler=delete_file,
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
