"""
Example Sophia plugin. Copy this file into the "plugins" folder of your
data folder (~/Library/Application Support/Sophia/plugins on macOS,
%APPDATA%\\Sophia\\plugins on Windows) without the leading underscore,
then allow it:  sophia --trust-plugin example_plugin.py

A plugin defines TOOLS (a list of Tool objects) or a
register(registry, services) function. Each tool's handler receives the
context first, then the arguments, and returns (ok, message).
"""

import random

from app.tools.registry import Tool

TOOLS = [
    Tool(
        name="roll_dice",
        description="Roll a die with the given number of sides (default 6).",
        parameters={"sides": {"type": "integer"}},
        handler=lambda context, sides=6: (
            True, f"Rolled a {random.randint(1, max(2, int(sides)))}."
        ),
    )
]
