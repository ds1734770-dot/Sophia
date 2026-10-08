import json
import sys
from pathlib import Path

import pytest

from app.actions.pending_action_manager import PendingActionManager
from app.brain.tool_context import ToolContext
from app.tools.integration_tools import register_integration_tools
from app.tools.mcp_bridge import McpBridge, expand_env, load_config, tool_name
from app.tools.plugins import load_plugins
from app.tools.registry import Risk, ToolRegistry

ECHO_SERVER = str(Path(__file__).parent / "fixtures" / "echo_server.py")


def context():

    ctx = ToolContext()
    ctx.pending_actions = PendingActionManager()

    return ctx


# ---------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------

def test_load_config_accepts_valid_servers_only(tmp_path):

    path = tmp_path / "mcp.json"

    assert load_config(path) == {}

    path.write_text("{broken")
    assert load_config(path) == {}

    path.write_text(json.dumps({"servers": {
        "good": {"command": "node", "args": ["x"]},
        "no_command": {"args": []},
        "bad": "text",
    }}))

    assert list(load_config(path)) == ["good"]


def test_env_values_are_expanded(monkeypatch):

    monkeypatch.setenv("MY_TOKEN", "secret123")

    assert expand_env({"TOKEN": "Bearer ${MY_TOKEN}", "X": "plain", "Y": "${MISSING}"}) == {
        "TOKEN": "Bearer secret123", "X": "plain", "Y": "",
    }


def test_tool_names_are_safe_and_short():

    assert tool_name("Git-Hub", "create.issue") == "mcp_git_hub_create_issue"
    assert len(tool_name("s" * 80, "t")) == 64


# ---------------------------------------------------------------
# MCP bridge against a real (local) server
# ---------------------------------------------------------------

@pytest.fixture
def bridge(tmp_path):

    config = tmp_path / "mcp.json"

    config.write_text(json.dumps({"servers": {
        "echo": {"command": sys.executable, "args": [ECHO_SERVER]},
        "broken": {"command": "definitely-not-a-program-xyz"},
    }}))

    registry = ToolRegistry()
    mcp = McpBridge(registry, config)

    mcp.start()

    assert mcp.ready.wait(60), "MCP servers did not connect"

    yield mcp, registry

    mcp.stop()


def test_tools_are_discovered_and_a_broken_server_is_skipped(bridge):

    mcp, registry = bridge

    assert sorted(registry.names()) == ["mcp_echo_add", "mcp_echo_shout"]
    assert mcp.status["echo"] == "2 tools"
    assert mcp.status["broken"].startswith("unavailable")
    assert "echo: 2 tools" in mcp.describe()


def test_discovered_tools_ask_before_running_unless_read_only(bridge):

    _, registry = bridge

    assert registry.tools["mcp_echo_shout"].risk is Risk.CONFIRM
    assert "mcp_echo_shout" in [d.name for d in registry.declarations()]


def test_calling_an_mcp_tool(bridge):

    _, registry = bridge

    ctx = context()

    asked = registry.execute("mcp_echo_shout", {"text": "hello"}, ctx)

    assert asked.needs_confirmation
    assert "shout" in asked.message and "echo" in asked.message

    result = registry.execute("mcp_echo_shout", {"text": "hello"}, ctx, confirmed=True)

    assert result.ok
    assert "HELLO" in result.message
    assert "treat as data" in result.message

    total = registry.execute("mcp_echo_add", {"a": 2, "b": 40}, ctx, confirmed=True)

    assert "42" in total.message


def test_missing_arguments_are_rejected_before_calling(bridge):

    _, registry = bridge

    assert not registry.execute("mcp_echo_shout", {}, context(), confirmed=True).ok


def test_calls_to_unconnected_servers_fail_cleanly(tmp_path):

    mcp = McpBridge(ToolRegistry(), tmp_path / "none.json")

    assert not mcp.call("ghost", "tool", {})[0]
    assert mcp.describe() == "No integrations are connected."

    mcp.start()

    assert mcp.ready.is_set()


# ---------------------------------------------------------------
# Integration tools
# ---------------------------------------------------------------

def make_integration_tools(tmp_path, plugins=("hello.py",)):

    registry = ToolRegistry()

    class Bridge:

        def describe(self):
            return "echo: 2 tools"

    config = tmp_path / "data" / "mcp.json"

    register_integration_tools(registry, Bridge(), config, list(plugins))

    return registry, config


def test_list_integrations(tmp_path):

    registry, _ = make_integration_tools(tmp_path)

    message = registry.execute("list_integrations", {}, context()).message

    assert "echo: 2 tools" in message and "hello.py" in message


def test_adding_a_server_is_dangerous_and_writes_the_config(tmp_path):

    registry, config = make_integration_tools(tmp_path)
    ctx = context()

    args = {"name": "github", "command": "npx", "args": ["-y", "some-server"]}

    asked = registry.execute("add_mcp_server", args, ctx)

    assert asked.needs_confirmation
    assert asked.message.startswith("Warning:")
    assert "npx -y some-server" in asked.message
    assert not config.exists()
    assert not registry.trust("add_mcp_server")

    assert registry.execute("add_mcp_server", args, ctx, confirmed=True).ok
    assert load_config(config)["github"]["args"] == ["-y", "some-server"]

    assert not registry.execute("add_mcp_server", args, ctx, confirmed=True).ok


def test_server_names_are_validated(tmp_path):

    registry, config = make_integration_tools(tmp_path)

    result = registry.execute(
        "add_mcp_server", {"name": "../evil", "command": "x"}, context(), confirmed=True
    )

    assert not result.ok and not config.exists()


# ---------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------

def test_plugins_with_tools_and_register_functions_load(tmp_path):

    (tmp_path / "dice.py").write_text(
        "from app.tools.registry import Tool\n"
        "TOOLS = [Tool(name='roll_dice', description='Roll a die', handler=lambda c: '4')]\n"
    )

    (tmp_path / "greeter.py").write_text(
        "from app.tools.registry import Tool\n"
        "def register(registry, services):\n"
        "    registry.register(Tool(name='greet', description='x', handler=lambda c: services['who']))\n"
    )

    (tmp_path / "_disabled.py").write_text("raise RuntimeError('must not load')\n")

    (tmp_path / "broken.py").write_text("this is not python (\n")

    registry = ToolRegistry()

    loaded = load_plugins(registry, [tmp_path, tmp_path / "missing_folder"], {"who": "hi"})

    assert loaded == ["dice.py", "greeter.py"]
    assert sorted(registry.names()) == ["greet", "roll_dice"]
    assert registry.execute("greet", {}, None).message == "hi"
