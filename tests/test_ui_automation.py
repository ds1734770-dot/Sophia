from app.brain.tool_context import ToolContext
from app.computer.ui_automation import Element, ScreenElements
from app.tools.registry import Risk, ToolRegistry
from app.tools.screen_tools import register_element_tools


class FakeBackend:

    def __init__(self, elements, title="Mail - App", press_works=True):
        self.elements = elements
        self.window_title = title
        self.press_works = press_works
        self.pressed = []
        self.values = []
        self.asked = []

    def window(self, title=None):
        self.asked.append(title)
        return None if title == "missing" else object()

    def title(self, window):
        return self.window_title

    def walk(self, window):
        return [Element(**vars(e)) for e in self.elements]

    def press(self, element):
        self.pressed.append(element.name)
        return self.press_works

    def set_value(self, element, text):
        self.values.append((element.name, text))
        return True


def el(i, kind, name, x=100, y=100, enabled=True, password=False):
    return Element(i, kind, name, x, y, 80, 24, enabled, password)


class Mouse:
    def __init__(self):
        self.clicks = []

    def click(self, x, y, button="left", double=False):
        self.clicks.append((x, y, button, double))


def make(elements, **kw):

    backend = FakeBackend(elements, **kw)
    mouse = Mouse()
    typed = []

    return ScreenElements(backend, mouse, lambda t, e: typed.append((t, e))), backend, mouse, typed


def test_lists_controls_with_names_and_flags_data():

    se, *_ = make([el(1, "Button", "Send"), el(2, "Edit", "To", y=50, enabled=False)])

    ok, text = se.list()

    assert ok
    assert '[1] Button "Send"' in text and '[2] Edit "To" [disabled]' in text
    assert "not instructions" in text


def test_duplicate_controls_are_collapsed():

    se, *_ = make([el(1, "MenuItem", "File"), el(2, "Button", "File")])

    assert se.list()[1].count('"File"') == 1


def test_click_presses_through_the_pattern_without_the_mouse():

    se, backend, mouse, _ = make([el(1, "Button", "Send")])

    ok, message = se.click("send")

    assert ok and backend.pressed == ["Send"] and mouse.clicks == []


def test_click_falls_back_to_the_mouse_when_there_is_no_pattern():

    se, backend, mouse, _ = make([el(1, "Button", "Send", x=300, y=200)], press_works=False)

    assert se.click("Send")[0]
    assert mouse.clicks == [(300, 200, "left", False)]


def test_right_click_and_double_click_use_the_mouse():

    se, backend, mouse, _ = make([el(1, "ListItem", "report.pdf", x=50, y=60)])

    se.click("report.pdf", button="right")
    se.click("report.pdf", double=True)

    assert backend.pressed == []
    assert mouse.clicks == [(50, 60, "right", False), (50, 60, "left", True)]


def test_exact_name_beats_partial_matches():

    se, backend, *_ = make([el(1, "Button", "Send later", y=10), el(2, "Button", "Send", y=40)])

    se.click("send")

    assert backend.pressed == ["Send"]


def test_two_identical_names_are_ambiguous_not_guessed():

    se, backend, *_ = make([el(1, "Button", "Delete", y=10), el(2, "Button", "Delete", y=200)])

    ok, message = se.click("delete")

    assert not ok and "More than one" in message and backend.pressed == []


def test_missing_and_disabled_controls_are_explained():

    se, *_ = make([el(1, "Button", "Pay", enabled=False)])

    assert "No control named" in se.click("nothing")[1]
    assert "disabled" in se.click("pay")[1]


def test_unknown_window():

    se, *_ = make([])

    assert se.click("x", "missing") == (False, "I couldn't find that window.")


def test_sophias_own_window_is_off_limits():

    se, *_ = make([el(1, "Button", "Send")], title="Sophia")

    ok, message = se.list()

    assert not ok and "no controls" in message


def test_typing_sets_the_value_directly():

    se, backend, mouse, typed = make([el(1, "Edit", "Search")])

    assert se.type_into("search", "porsche")[0]
    assert backend.values == [("Search", "porsche")] and typed == []


def test_typing_with_enter_clicks_and_types_for_real():

    se, backend, mouse, typed = make([el(1, "Edit", "Search", x=40, y=9)])

    assert se.type_into("search", "porsche", press_enter=True)[0]
    assert mouse.clicks == [(40, 9, "left", False)] and typed == [("porsche", True)]


def test_no_name_means_the_first_text_box_but_never_a_password():

    se, backend, *_ = make([el(1, "Button", "Go"), el(2, "Edit", "Password", password=True)])

    ok, message = se.type_into(None, "secret")

    assert not ok and "password" in message and backend.values == []


def test_tools_are_registered_with_the_right_tiers():

    se, *_ = make([])
    registry = ToolRegistry()
    policy = {"confirm": False}

    register_element_tools(registry, se, policy)

    assert registry.tools["click_element"].risk is Risk.CONFIRM
    assert registry.tools["type_in_element"].risk is Risk.CONFIRM

    reading = registry.tools["list_screen_elements"]

    assert reading.risk_fn({}) is Risk.SAFE

    policy["confirm"] = True

    assert reading.risk_fn({}) is Risk.CONFIRM


def test_click_element_asks_first_then_acts():

    se, backend, *_ = make([el(1, "Button", "Send")])
    registry = ToolRegistry()

    register_element_tools(registry, se, {})

    context = ToolContext()

    from app.actions.pending_action_manager import PendingActionManager
    context.pending_actions = PendingActionManager()
    context.registry = registry

    asked = registry.execute("click_element", {"name": "Send"}, context)

    assert asked.needs_confirmation and backend.pressed == []

    done = registry.execute("click_element", {"name": "Send"}, context, confirmed=True)

    assert done.ok and backend.pressed == ["Send"]
