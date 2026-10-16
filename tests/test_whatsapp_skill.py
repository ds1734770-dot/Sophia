import pytest

from app.agent.control import AgentControl
from app.agent.guard import ScreenGuard
from app.agent.observer import ScreenObserver
from app.agent.skills import WhatsAppSkill, primary_name
from app.brain.tool_context import ToolContext
from app.computer.ui_automation import Element, ScreenElements
from tests.test_screen_agent import FakeElements, el


def page(*elements, title="WhatsApp Web - Google Chrome", process="chrome.exe"):

    return (title, process, list(elements))


SEARCH = lambda: el(1, "Edit", "Search or start a new chat")

CHAT_LIST = lambda: page(SEARCH(), el(2, "ListItem", "Mom | 9:10 | ok"))

RESULTS = lambda: page(
    SEARCH(),
    el(2, "ListItem", "Srino | 10:42 | see you"),
    el(3, "ListItem", "Srino | 10:42 | see you"),               # the same chat listed twice
)

CHAT = lambda: page(
    el(1, "Button", "Video call"), el(2, "Button", "Voice call"), el(3, "Edit", "Type a message"),
)

CALLING = lambda: page(el(1, "Button", "End call"), el(2, "Button", "Mute"))


def make(pages, opened=None, **kwargs):

    elements = FakeElements(pages)
    observer = ScreenObserver(elements)
    control = AgentControl()

    def open_app(name):

        if opened is not None:
            opened.append(name)

        # opening WhatsApp brings up its chat list
        elements.pages = [CHAT_LIST()] + elements.pages[1:]
        elements.position = 0

        return True, f"Opening {name}..."

    skill = WhatsAppSkill(
        observer, elements, control, ScreenGuard(), open_app,
        sleep=lambda s: None, open_wait=1.0, ui_wait=0.2, **kwargs,
    )

    return skill, elements, control


# ---------------------------------------------------------------
# Calling
# ---------------------------------------------------------------

def test_open_whatsapp_and_call_srino():

    skill, elements, control = make([CHAT_LIST(), RESULTS(), CHAT(), CALLING()])

    ok, message = skill.call("srino")

    assert ok and message == "Calling Srino on WhatsApp."

    # it typed the name into the search box, opened the chat and pressed Voice call
    assert elements.typed == [("Search or start a new chat", "srino", False)]
    assert [name for name, *_ in elements.pressed] == ["Srino | 10:42 | see you", "Voice call"]

    assert not control.active


def test_a_video_call_presses_the_video_button():

    skill, elements, control = make([CHAT_LIST(), RESULTS(), CHAT(), CALLING()])

    ok, message = skill.call("Srino", video=True)

    assert ok and message == "Video calling Srino on WhatsApp."
    assert elements.pressed[-1][0] == "Video call"


def test_whatsapp_is_opened_first_when_it_is_not_in_front():

    opened = []

    skill, elements, control = make(
        [("Untitled - Notepad", "notepad.exe", []), RESULTS(), CHAT(), CALLING()], opened
    )

    ok, message = skill.call("Srino")

    assert opened == ["WhatsApp"] and ok


def test_it_does_not_reopen_whatsapp_when_it_is_already_in_front():

    opened = []

    skill, *_ = make([CHAT_LIST(), RESULTS(), CHAT(), CALLING()], opened)

    # the first page is already WhatsApp
    assert skill.call("Srino")[0] and opened == []


def test_a_dry_run_stops_before_pressing_call():

    skill, elements, control = make([CHAT_LIST(), RESULTS(), CHAT()])

    ok, message = skill.call("Srino", dry_run=True)

    assert ok and "Ready to call Srino" in message
    assert [name for name, *_ in elements.pressed] == ["Srino | 10:42 | see you"]      # only the chat


def test_a_call_whose_screen_cannot_be_confirmed_says_so():

    skill, elements, control = make([CHAT_LIST(), RESULTS(), CHAT(), CHAT()])

    ok, message = skill.call("Srino")

    assert ok and "can't see the call screen to confirm" in message


# ---------------------------------------------------------------
# When it cannot
# ---------------------------------------------------------------

def test_not_signed_in_is_explained():

    skill, *_ = make([page(el(1, "Text", "Use WhatsApp on your computer"), el(2, "Button", "Link with phone number"))])

    skill.elements.pages = [page(el(1, "Hyperlink", "Use WhatsApp on your computer"))]

    ok, message = skill.call("Srino")

    assert not ok and "not signed in" in message and "QR code" in message


def test_a_missing_contact_is_reported():

    skill, *_ = make([CHAT_LIST(), page(SEARCH(), el(2, "ListItem", "Mom | hi"))])

    ok, message = skill.call("Zed")

    assert not ok and "couldn't find 'Zed'" in message


def test_two_different_people_are_asked_about_not_guessed():

    skill, elements, control = make([
        CHAT_LIST(),
        page(SEARCH(), el(2, "ListItem", "Srino Kumar | hi"), el(3, "ListItem", "Srinoj Rao | yo")),
    ])

    ok, message = skill.call("srino")

    assert not ok and "more than one match" in message and "Srino Kumar" in message and "Srinoj Rao" in message
    assert elements.pressed == []


def test_an_exact_name_wins_over_longer_matches():

    skill, elements, control = make([
        CHAT_LIST(),
        page(SEARCH(), el(2, "ListItem", "Srino | hi"), el(3, "ListItem", "Srino Kumar | yo")),
        CHAT(), CALLING(),
    ])

    ok, message = skill.call("srino")

    assert ok and elements.pressed[0][0] == "Srino | hi"


def test_no_call_button_is_reported():

    skill, *_ = make([CHAT_LIST(), RESULTS(), page(el(1, "Edit", "Type a message"))])

    ok, message = skill.call("Srino")

    assert not ok and "couldn't find the voice call button" in message


def test_the_call_buttons_in_the_results_are_not_mistaken_for_chats():

    skill, elements, control = make([
        CHAT_LIST(),
        page(SEARCH(), el(2, "Button", "Voice call with Srino"), el(3, "ListItem", "Srino | hi")),
        CHAT(), CALLING(),
    ])

    assert skill.call("srino")[0] and elements.pressed[0][0] == "Srino | hi"


# ---------------------------------------------------------------
# Messages
# ---------------------------------------------------------------

def test_a_message_is_typed_and_sent():

    skill, elements, control = make([CHAT_LIST(), RESULTS(), CHAT()])

    ok, message = skill.message("Srino", "I'll be late tonight")

    assert ok and message == "Sent Srino a WhatsApp message: I'll be late tonight"
    assert elements.typed[-1] == ("Type a message", "I'll be late tonight", True)


def test_a_chat_without_a_message_box_is_reported():

    skill, *_ = make([CHAT_LIST(), RESULTS(), page(el(1, "Button", "Voice call"))])

    ok, message = skill.message("Srino", "hi")

    assert not ok and "message box" in message


# ---------------------------------------------------------------
# Stop and safety
# ---------------------------------------------------------------

def test_the_stop_switch_ends_it_before_anything_more_is_done():

    skill, elements, control = make([CHAT_LIST(), RESULTS(), CHAT(), CALLING()])

    original = elements.type_to

    def type_then_stop(element, text, press_enter=False):

        result = original(element, text, press_enter)

        control.stop("You pressed Stop.")

        return result

    elements.type_to = type_then_stop

    ok, message = skill.call("Srino")

    assert not ok and message == "You pressed Stop."
    assert elements.pressed == []                          # no chat opened, no call made


def test_a_forbidden_window_stops_it():

    skill, elements, control = make([page(el(1, "Button", "Pay"), title="HDFC NetBanking - Google Chrome")])

    ok, message = skill.call("Srino")

    assert not ok and "banking or payment" in message and elements.typed == []


def test_a_task_shows_the_overlay_hooks():

    skill, elements, control = make([CHAT_LIST(), RESULTS(), CHAT(), CALLING()])

    seen = []

    control.listeners.append(lambda active: seen.append((active, control.goal)))

    skill.call("Srino")

    assert seen == [(True, "voice call Srino on WhatsApp"), (False, "voice call Srino on WhatsApp")]


def test_chat_rows_are_read_by_the_name_before_the_bar():

    assert primary_name("Srino | 10:42 | see you") == "Srino"
    assert primary_name("Srino") == "Srino"


# ---------------------------------------------------------------
# Typing into web pages needs real keystrokes
# ---------------------------------------------------------------

class SpyBackend:

    def __init__(self, process):

        self.process = process
        self.values = []

    def window(self, title=None):
        return object()

    def title(self, window):
        return "Some window"

    def process_name(self, window):
        return self.process

    def walk(self, window):
        return [Element(1, "Edit", "Search", 10, 10, 80, 20)]

    def set_value(self, element, text):
        self.values.append(text)
        return True


class SpyMouse:

    def __init__(self):
        self.events = []

    def click(self, x, y, button="left", double=False):
        self.events.append(("click", x, y))

    def hotkey(self, *keys):
        self.events.append(("hotkey",) + keys)


def typing(process, kind="Edit"):

    backend = SpyBackend(process)
    mouse = SpyMouse()
    typed = []

    elements = ScreenElements(backend, mouse, lambda text, enter=False: typed.append((text, enter)))

    elements.snapshot()

    element = Element(1, kind, "Search", 10, 10, 80, 20)

    elements.type_to(element, "srino")

    return backend, mouse, typed


def test_a_web_page_box_is_typed_with_keystrokes_after_clearing_it():

    backend, mouse, typed = typing("chrome.exe")

    assert backend.values == []                            # the page would not notice a set value
    assert mouse.events == [("click", 10, 10), ("hotkey", "ctrl", "a")]
    assert typed == [("srino", False)]


def test_a_native_box_is_set_directly():

    backend, mouse, typed = typing("notepad.exe")

    assert backend.values == ["srino"] and typed == [] and mouse.events == []


def test_a_document_is_never_cleared_before_typing():

    backend, mouse, typed = typing("chrome.exe", kind="Document")

    assert ("hotkey", "ctrl", "a") not in mouse.events and typed == [("srino", False)]


# ---------------------------------------------------------------
# Spoken to the quick engine
# ---------------------------------------------------------------

def test_the_spoken_request_reaches_the_skill():

    from app.brain.engines.quick_engine import QuickEngine
    from app.tools.registry import Tool, ToolRegistry

    asked = []

    registry = ToolRegistry()

    registry.register(Tool(
        name="whatsapp_call", description="c",
        parameters={"contact": {"type": "string"}, "video": {"type": "boolean"}},
        required=["contact"],
        handler=lambda context, contact, video=False: asked.append((contact, video)) or (False, "WhatsApp is not signed in."),
    ))

    context = ToolContext()
    context.registry = registry

    result = QuickEngine().execute("Open WhatsApp and call Srino.", context)

    assert asked == [("srino", False)]

    # the reason is shown to the user (it is not retried with the AI)
    assert result == {"handled": True, "response": "WhatsApp is not signed in."}
