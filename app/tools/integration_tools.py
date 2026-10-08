"""
Tools for seeing and adding integrations (MCP servers and plugins).
"""

import json
import re

from app.tools.mcp_bridge import load_config
from app.tools.registry import Risk, Tool

STRING = {"type": "string"}


def register_integration_tools(registry, bridge, config_path, plugins):

    def list_integrations(context):

        lines = ["Connected integrations (MCP servers):", bridge.describe()]

        lines.append("")
        lines.append(
            "Plugins loaded: " + (", ".join(plugins) if plugins else "none")
        )

        return True, "\n".join(lines)

    def add_mcp_server(context, name, command, args=None):

        if not re.fullmatch(r"[a-z0-9_-]{1,30}", name):
            return False, "The name must be lowercase letters, digits, - or _."

        servers = load_config(config_path)

        if name in servers:
            return False, f"An integration called '{name}' already exists."

        try:

            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        except (OSError, ValueError):
            data = {}

        data.setdefault("servers", {})[name] = {
            "command": command,
            "args": [str(a) for a in (args or [])],
        }

        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return True, (
            f"Added '{name}'. Restart Sophia to connect it. If it needs an "
            "API key, add an \"env\" entry for it in data/mcp.json yourself."
        )

    registry.register(Tool(
        name="list_integrations",
        description="Show which MCP integrations and plugins are connected.",
        handler=list_integrations,
    ))

    registry.register(Tool(
        name="add_mcp_server",
        description=(
            "Add an MCP integration (a server that gives Sophia more "
            "tools, such as GitHub or Google Drive). It runs the given "
            "command every time Sophia starts, so only add servers from "
            "sources the user trusts. Takes effect after a restart."
        ),
        parameters={
            "name": STRING,
            "command": STRING,
            "args": {"type": "array", "items": {"type": "string"}},
        },
        required=["name", "command"],
        risk=Risk.DANGEROUS,
        preview=lambda a: (
            "I'm about to add an integration that will run this program "
            f"every time Sophia starts: {a['command']} {' '.join(a.get('args') or [])}"
        ),
        handler=add_mcp_server,
    ))
