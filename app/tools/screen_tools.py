"""
Tools that act on the screen: click, type, press keys, scroll.

They are CONFIRM-tier (the user can say "always" for the session when
they want Sophia to work through a task on her own).
"""

from app.tools.registry import Risk, Tool

BOOLEAN = {"type": "boolean"}

STRING = {"type": "string"}


def autonomy_risk(screen_policy):
    """
    The tier of an action on the screen: none when she is fully autonomous
    (the default), a confirmation when the user chose to be asked.
    """

    policy = screen_policy if screen_policy is not None else {}

    return lambda args: Risk.SAFE if policy.get("autonomy", "auto") == "auto" else Risk.CONFIRM


GUARDED = ("click_on_screen", "type_text", "press_keys", "click_element", "type_in_element")


def apply_guard(registry, elements, guard, screen_policy):
    """
    Every click and keystroke is checked against the places she never
    touches, and follows the autonomy setting.
    """

    risk = autonomy_risk(screen_policy)

    for name in GUARDED:

        tool = registry.tools.get(name)

        if tool is None:
            continue

        tool.risk_fn = risk

        if guard is None or elements is None:
            continue

        inner = tool.handler

        def guarded(context, _inner=inner, _name=name, **args):

            title, process = elements.current_window()

            allowed, why = guard.check_window(title, process)

            if not allowed:
                return False, f"I won't do that here: {why}"

            # typing: never into a secret
            if _name in ("type_in_element", "type_text"):

                if _name == "type_in_element":
                    field = (args.get("name") or "", False)

                else:
                    field = elements.focused_field() or ("", False)

                allowed, why = guard.check_field(*field)

                if not allowed:
                    return False, why

            return _inner(context, **args)

        tool.handler = guarded


def register_screen_tools(registry, screen, elements=None, screen_policy=None, guard=None):

    if elements is not None:
        register_element_tools(registry, elements, screen_policy)

    _register_screen_tools(registry, screen)

    apply_guard(registry, elements, guard, screen_policy)


def _register_screen_tools(registry, screen):

    registry.register(Tool(
        name="click_on_screen",
        description=(
            "Click something visible on the screen, described in words "
            "(for example 'the Send button', 'the search box', 'the "
            "first video'). Sophia looks at a screenshot to find it, "
            "which is slower and less exact than click_element: use "
            "this only when click_element cannot find the control (web "
            "page content, images, custom-drawn windows). After acting, "
            "check the result with look_at_screen before continuing."
        ),
        parameters={
            "target": STRING,
            "button": {"type": "string", "enum": ["left", "right"]},
            "double_click": {"type": "boolean"},
        },
        required=["target"],
        risk=Risk.CONFIRM,
        preview=lambda a: f"I'm about to click on '{a['target']}' on your screen.",
        handler=lambda context, target, button="left", double_click=False: screen.click_on(
            target, button=button, double=bool(double_click)
        ),
    ))

    registry.register(Tool(
        name="type_text",
        description=(
            "Type text with the keyboard into whatever has focus. Click "
            "the right field first. press_enter=true presses Enter after."
        ),
        parameters={"text": STRING, "press_enter": {"type": "boolean"}},
        required=["text"],
        risk=Risk.CONFIRM,
        preview=lambda a: (
            f"I'm about to type \"{a['text'][:80]}\""
            + ("..." if len(a["text"]) > 80 else "")
            + (" and press Enter" if a.get("press_enter") else "")
            + " on your computer."
        ),
        handler=lambda context, text, press_enter=False: screen.type_text(
            text, bool(press_enter)
        ),
    ))

    registry.register(Tool(
        name="press_keys",
        description=(
            "Press a key or shortcut, like enter, esc, tab, ctrl+c, "
            "ctrl+v, alt+tab, win+d, ctrl+shift+t (up to 4 keys joined "
            "with +)."
        ),
        parameters={"keys": STRING},
        required=["keys"],
        risk=Risk.CONFIRM,
        preview=lambda a: f"I'm about to press {a['keys']}.",
        handler=lambda context, keys: screen.press_keys(keys),
    ))

    registry.register(Tool(
        name="scroll_screen",
        description="Scroll the window under the mouse up or down.",
        parameters={
            "direction": {"type": "string", "enum": ["up", "down"]},
            "amount": {"type": "integer"},
        },
        required=["direction"],
        handler=lambda context, direction, amount=5: screen.scroll(direction, amount),
    ))


def register_element_tools(registry, elements, screen_policy=None):
    """
    Controls found through the Windows accessibility tree: exact names,
    no screenshot, no AI request.
    """

    def reading_risk(args):

        # the control names reach Gemini, like a screenshot would
        return Risk.CONFIRM if (screen_policy or {}).get("confirm") else Risk.SAFE

    registry.register(Tool(
        name="list_screen_elements",
        description=(
            "List the buttons, menus, tabs, links and text boxes of the "
            "window the user is working in (or another window by title), "
            "with exact names. Fast; no screenshot. Use it to see what "
            "can be clicked, then click_element or type_in_element."
        ),
        parameters={"window": STRING},
        risk=Risk.CONFIRM,
        risk_fn=reading_risk,
        preview=lambda a: "I'm about to read the controls of the window you are using.",
        handler=lambda context, window=None: elements.list(window),
    ))

    registry.register(Tool(
        name="click_element",
        description=(
            "Click a button, menu item, tab, link, checkbox or list item "
            "by its name in the window the user is working in (or "
            "another window by title). The first choice for operating "
            "programs: exact, fast, and it usually does not even move "
            "the mouse. If it says nothing matches, try "
            "list_screen_elements, then click_on_screen."
        ),
        parameters={
            "name": STRING,
            "window": STRING,
            "button": {"type": "string", "enum": ["left", "right"]},
            "double_click": BOOLEAN,
        },
        required=["name"],
        risk=Risk.CONFIRM,
        preview=lambda a: f"I'm about to click '{a['name']}' in the window you are using.",
        handler=lambda context, name, window=None, button="left", double_click=False: elements.click(
            name, window, button=button, double=bool(double_click)
        ),
    ))

    registry.register(Tool(
        name="type_in_element",
        description=(
            "Put text into a text box or search field by its name (or "
            "the first text box when no name is given). It does not "
            "touch password fields. press_enter=true presses Enter after."
        ),
        parameters={
            "text": STRING,
            "name": STRING,
            "window": STRING,
            "press_enter": BOOLEAN,
        },
        required=["text"],
        risk=Risk.CONFIRM,
        preview=lambda a: (
            f"I'm about to type \"{a['text'][:80]}\""
            + ("..." if len(a["text"]) > 80 else "")
            + (f" into '{a['name']}'" if a.get("name") else " into the text box")
            + (" and press Enter" if a.get("press_enter") else "")
            + "."
        ),
        handler=lambda context, text, name=None, window=None, press_enter=False: elements.type_into(
            name, text, window, press_enter=bool(press_enter)
        ),
    ))
