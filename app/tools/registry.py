"""
Tool registry: the single place where Sophia's abilities are declared
and where safety tiers are enforced.

Every action Sophia can take on the computer (whether Gemini asks for it
or a local command triggers it) goes through ToolRegistry.execute, so a
risky action can never skip its confirmation step.
"""

from __future__ import annotations

import itertools
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, cast

from google.genai import types

if TYPE_CHECKING:
    from app.actions.pending_action_manager import PendingActionManager
    from app.brain.tool_context import ToolContext

log = logging.getLogger("sophia.tools")


class Risk(Enum):
    # Runs immediately: read-only or easily undone
    SAFE = "safe"

    # Asks the user first: changes things, but can be undone
    CONFIRM = "confirm"

    # Always asks, with a clear warning: hard to undo
    DANGEROUS = "dangerous"


class ToolBlocked(Exception):
    """
    Raised by a tool's risk_fn when the request must be refused
    outright. The message is shown to the user.
    """


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[..., object]
    parameters: dict[str, object] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    risk: Risk = Risk.SAFE

    # Builds the sentence shown when confirmation is needed
    preview: Callable[[dict[str, object]], str] | None = None

    # Optional: decides the tier from the arguments (may raise
    # ToolBlocked). Overrides `risk`.
    risk_fn: Callable[[dict[str, object]], Risk] | None = None

    # May the user answer "always" so it stops asking this session?
    trustable: bool = True

    def declaration(self) -> types.FunctionDeclaration:

        schema = {
            "type": "object",
            "properties": self.parameters,
            "required": self.required,
        }

        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=schema,
        )

    def describe(self, args: dict[str, object]) -> str:

        if self.preview is not None:
            return self.preview(args)

        details = ", ".join(f"{k}={v!r}" for k, v in args.items())

        return f"{self.name}({details})"


@dataclass
class ToolResult:
    ok: bool
    message: str
    needs_confirmation: bool = False

    # The tool ends the model's loop and `message` is the final answer
    # (a task finished, the user pressed stop, a forbidden place was reached)
    stop: bool = False


# Tools that only look things up: several can run at the same moment
PARALLEL_SAFE = frozenset({
    "get_current_time", "calculate", "web_search", "read_webpage", "get_weather",
    "find_files", "list_directory", "read_file", "list_memories", "get_schedule",
    "list_notes", "list_todos", "list_timers", "list_routines", "system_status",
    "list_integrations", "clipboard_read", "convert_units", "convert_currency",
    "define_word", "wikipedia_summary", "news_headlines", "list_processes",
    "network_status", "folder_sizes", "recent_files", "agent_status", "connect_agents",
})


class ToolRegistry:

    def __init__(self, audit: Callable[[str, dict[str, object], ToolResult, bool], None] | None = None) -> None:

        self.tools: dict[str, Tool] = {}

        # Tools the user said "always" to, for this session only
        self.trusted: set[str] = set()

        # Optional callable(name, args, result, confirmed) for the log
        self.audit = audit

        # Callables told when a tool starts and ends, for live progress
        # in the interface: observer(event) with a dict holding phase
        # ("start" or "end"), token, name, args and, at the end, ok,
        # message and seconds.
        self.observers: list[Callable[[dict[str, object]], None]] = []
        self._tokens = itertools.count(1)

    # ------------------------------------------------

    def register(self, tool: Tool) -> None:

        self.tools[tool.name] = tool

    def _notify(self, event: dict[str, object]) -> None:

        for observer in list(self.observers):

            try:
                observer(event)

            except Exception:
                log.debug("Tool observer failed", exc_info=True)

    def names(self) -> list[str]:

        return list(self.tools)

    def declarations(self) -> list[types.FunctionDeclaration]:

        # a copy: integrations may add tools while a request is built
        return [tool.declaration() for tool in list(self.tools.values())]

    def is_safe(self, name: str, args: Mapping[str, object] | None = None) -> bool:
        """
        Is this a read-only lookup that may run alongside others?
        """

        tool = self.tools.get(name)

        return (
            tool is not None
            and name in PARALLEL_SAFE
            and tool.risk is Risk.SAFE
            and tool.risk_fn is None
        )

    def safe_only(self) -> ToolRegistry:
        """
        A registry with just the SAFE-tier tools, for background work
        (routines) that must never ask or change anything.
        """

        view = ToolRegistry(audit=self.audit)

        for tool in self.tools.values():

            if tool.risk is Risk.SAFE and tool.risk_fn is None:
                view.register(tool)

        return view

    def trust(self, name: str) -> bool:
        """
        Stop asking for this tool for the rest of the session. Only
        CONFIRM-tier tools marked trustable can be trusted; dangerous
        ones always ask.
        """

        tool = self.tools.get(name)

        if tool is None or not tool.trustable or tool.risk is not Risk.CONFIRM:
            return False

        self.trusted.add(name)

        return True

    # ------------------------------------------------

    def execute(
        self, name: str, args: Mapping[str, object] | None, context: ToolContext, confirmed: bool = False
    ) -> ToolResult:
        """
        Run a tool. Tools above the SAFE tier are held back as a pending
        confirmation unless `confirmed` is True (or the user trusted the
        tool for this session).
        """

        tool = self.tools.get(name)

        if tool is None:
            return ToolResult(False, f"Unknown tool '{name}'.")

        args = dict(args or {})

        missing = [p for p in tool.required if p not in args]

        if missing:
            return ToolResult(
                False,
                f"Missing required argument(s): {', '.join(missing)}.",
            )

        unexpected = [a for a in args if a not in tool.parameters]

        if unexpected:
            return ToolResult(
                False,
                f"Unexpected argument(s): {', '.join(unexpected)}.",
            )

        try:

            risk = tool.risk_fn(args) if tool.risk_fn else tool.risk

        except ToolBlocked as e:

            result = ToolResult(False, str(e))

            self._audit(name, args, result, confirmed)

            return result

        if (
            risk is Risk.CONFIRM
            and tool.trustable
            and name in self.trusted
        ):
            confirmed = True

        if risk is not Risk.SAFE and not confirmed:

            return self._ask_confirmation(tool, risk, args, context)

        token = next(self._tokens)
        started = time.monotonic()

        self._notify({"phase": "start", "token": token, "name": name, "args": args})

        try:

            outcome = tool.handler(context, **args)

        except Exception as e:

            log.exception("Tool %s failed", name)

            result = ToolResult(False, f"{tool.name} failed: {e}")

            self._audit(name, args, result, confirmed)

            self._finish(token, name, args, result, started)

            return result

        if isinstance(outcome, ToolResult):
            result = outcome

        elif isinstance(outcome, tuple):
            ok, message = outcome
            result = ToolResult(bool(ok), str(message))

        else:
            result = ToolResult(True, str(outcome))

        self._audit(name, args, result, confirmed)

        self._finish(token, name, args, result, started)

        return result

    def _finish(self, token: int, name: str, args: dict[str, object], result: ToolResult, started: float) -> None:

        self._notify({
            "phase": "end", "token": token, "name": name, "args": args,
            "ok": result.ok, "message": result.message,
            "seconds": time.monotonic() - started,
        })

    # ------------------------------------------------

    def _audit(self, name: str, args: dict[str, object], result: ToolResult, confirmed: bool) -> None:

        if self.audit is None:
            return

        try:
            self.audit(name, args, result, confirmed)

        except Exception:
            log.exception("Audit log failed")

    def _ask_confirmation(self, tool: Tool, risk: Risk, args: dict[str, object], context: ToolContext) -> ToolResult:

        prompt = tool.describe(args)

        if risk is Risk.DANGEROUS:
            prompt = f"Warning: {prompt}"

        # The interactive context installs a manager before running tools that can ask for confirmation.
        pending_actions = cast("PendingActionManager", context.pending_actions)
        pending_actions.start(
            action="confirm",
            matches=[],
            data={
                "tool": tool.name,
                "args": args,
                "always": (
                    risk is Risk.CONFIRM
                    and tool.trustable
                    and tool.risk is Risk.CONFIRM
                ),
            },
        )

        options = (
            "Reply 'yes' to confirm, 'always' to stop asking for this "
            "kind of action this session, or 'no' to cancel."
            if pending_actions.current().data["always"]
            else "Reply 'yes' to confirm or 'no' to cancel."
        )

        return ToolResult(True, f"{prompt}\n\n{options}", needs_confirmation=True)
