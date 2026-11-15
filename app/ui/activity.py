"""
Turns a tool call into a line a person understands: an icon and a short
sentence ("Searching the web for ...", "Opening Notepad").
"""

from urllib.parse import urlparse


def _short(text, limit=48):

    text = " ".join(str(text or "").split())

    return text if len(text) <= limit else text[: limit - 1] + "…"


def _host(url):

    try:
        return urlparse(url).hostname or _short(url)

    except ValueError:
        return _short(url)


# name -> (icon, template). Templates use the call's arguments.
STEPS = {
    "open_application": ("🚀", "Opening {name}"),
    "close_application": ("✖", "Closing {name}"),
    "window_action": ("🪟", "{action} {name}"),
    "open_folder": ("📂", "Opening folder {name}"),
    "close_folder": ("📂", "Closing folder {name}"),
    "open_website": ("🌐", "Opening {url}"),
    "search_in_browser": ("🔎", "Searching for {query}"),
    "web_search": ("🔎", "Searching the web for {query}"),
    "read_webpage": ("📄", "Reading {url}"),
    "get_weather": ("⛅", "Checking the weather {city}"),
    "news_headlines": ("📰", "Getting the news {topic}"),
    "wikipedia_summary": ("📚", "Looking up {topic}"),
    "define_word": ("📖", "Defining {word}"),
    "convert_units": ("⚖", "Converting {value} {from_unit} to {to_unit}"),
    "convert_currency": ("💱", "Converting {amount} {from_currency} to {to_currency}"),
    "calculate": ("🧮", "Calculating {expression}"),
    "get_current_time": ("🕒", "Checking the time"),
    "find_files": ("🔍", "Searching your files for {query}"),
    "list_directory": ("📁", "Looking inside {path}"),
    "read_file": ("📄", "Reading {path}"),
    "write_file": ("✏", "Writing {path}"),
    "move_file": ("📦", "Moving {source}"),
    "copy_file": ("📋", "Copying {source}"),
    "rename_file": ("✏", "Renaming {path}"),
    "delete_file": ("🗑", "Deleting {path}"),
    "create_folder": ("📁", "Creating folder {name}"),
    "open_file": ("📄", "Opening {path}"),
    "launch_program": ("🚀", "Launching {path}"),
    "run_powershell": ("⌨", "Running a shell command"),
    "look_at_screen": ("👁", "Looking at your screen"),
    "take_screenshot": ("📸", "Taking a screenshot"),
    "list_screen_elements": ("🧭", "Reading the window's controls"),
    "click_element": ("🖱", "Clicking {name}"),
    "type_in_element": ("⌨", "Typing in {name}"),
    "click_on_screen": ("🖱", "Finding and clicking {target}"),
    "type_text": ("⌨", "Typing"),
    "press_keys": ("⌨", "Pressing {keys}"),
    "scroll_screen": ("↕", "Scrolling {direction}"),
    "set_volume": ("🔊", "Adjusting the volume"),
    "set_brightness": ("☀", "Adjusting the brightness"),
    "media_control": ("🎵", "Media: {action}"),
    "play_music": ("🎵", "Playing {query}"),
    "set_timer": ("⏱", "Starting a {minutes} minute timer"),
    "list_timers": ("⏱", "Checking timers"),
    "add_schedule": ("📅", "Adding to your schedule"),
    "get_schedule": ("📅", "Checking your schedule"),
    "add_note": ("📝", "Saving a note"),
    "list_notes": ("📝", "Reading your notes"),
    "add_todo": ("✅", "Adding a to-do"),
    "list_todos": ("✅", "Reading your to-dos"),
    "remember_fact": ("🧠", "Remembering that"),
    "list_memories": ("🧠", "Recalling what I know"),
    "system_status": ("💻", "Checking your PC"),
    "list_processes": ("📊", "Listing running programs"),
    "end_process": ("⛔", "Force-closing {name}"),
    "network_status": ("📶", "Checking the network"),
    "folder_sizes": ("📊", "Measuring folder sizes"),
    "recent_files": ("🕘", "Looking at recent files"),
    "zip_item": ("🗜", "Zipping {path}"),
    "unzip_item": ("🗜", "Unzipping {path}"),
    "clipboard_read": ("📋", "Reading the clipboard"),
    "clipboard_write": ("📋", "Copying to the clipboard"),
    "generate_password": ("🔑", "Generating a password"),
    "set_windows_theme": ("🌓", "Switching to {mode} mode"),
    "lock_computer": ("🔒", "Locking the computer"),
    "power_action": ("⏻", "{action}"),
    "undo_last_action": ("↩", "Undoing the last change"),
    "do_on_screen": ("🤖", "Working on your screen: {task}"),
    "screen_look": ("👁", "Looking at the screen"),
    "screen_read": ("📖", "Reading the screen"),
    "screen_describe": ("👁", "Looking closely at the screen"),
    "screen_click": ("🖱", "Clicking control {number}"),
    "screen_type": ("⌨", "Typing {text}"),
    "screen_press": ("⌨", "Pressing {keys}"),
    "screen_scroll": ("↕", "Scrolling {direction}"),
    "screen_open_app": ("🚀", "Opening {name}"),
    "screen_switch_window": ("🪟", "Switching to {title}"),
    "screen_click_visual": ("🖱", "Finding {description}"),
    "screen_wait": ("⏳", "Waiting"),
    "screen_finish": ("✅", "Finishing"),
    "screen_ask_user": ("❓", "Asking you something"),
}


class _Blank(dict):

    def __missing__(self, key):
        return ""


def describe_step(name, args=None):
    """
    (icon, sentence) for a tool call.
    """

    args = dict(args or {})

    if name.startswith("mcp_"):
        return "🔌", _short(name[4:].replace("_", " ").capitalize())

    icon, template = STEPS.get(name, ("⚙", name.replace("_", " ").capitalize()))

    values = _Blank({k: _short(v) for k, v in args.items()})

    if "url" in args:
        values["url"] = _host(str(args["url"]))

    if "city" in args and args["city"]:
        values["city"] = "in " + values["city"]

    if "topic" in args and args["topic"]:
        values["topic"] = "about " + values["topic"]

    if "action" in values and values["action"]:
        values["action"] = values["action"].capitalize()

    try:
        text = template.format_map(values)

    except (KeyError, ValueError, IndexError):
        text = name.replace("_", " ").capitalize()

    return icon, " ".join(text.split())
