"""
Tools that act on the screen: click, type, press keys, scroll.

They are CONFIRM-tier (the user can say "always" for the session when
they want Sophia to work through a task on her own).
"""

from app.tools.registry import Risk, Tool

STRING = {"type": "string"}


def register_screen_tools(registry, screen):

    registry.register(Tool(
        name="click_on_screen",
        description=(
            "Click something visible on the screen, described in words "
            "(for example 'the Send button', 'the search box', 'the "
            "first video'). Sophia looks at a screenshot to find it. "
            "After acting, check the result with look_at_screen before "
            "continuing."
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
