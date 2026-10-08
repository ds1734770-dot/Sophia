"""
Tool registry: the single place where Sophia's abilities are declared
and where safety tiers are enforced.

Every action Sophia can take on the computer (whether Gemini asks for it
or a local command triggers it) goes through ToolRegistry.execute, so a
risky action can never skip its confirmation step.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

from google.genai import types

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
    handler: object
    parameters: dict = field(default_factory=dict)
    required: list = field(default_factory=list)
    risk: Risk = Risk.SAFE

    # Builds the sentence shown when confirmation is needed
    preview: object = None

    # Optional: decides the tier from the arguments (may raise
    # ToolBlocked). Overrides `risk`.
    risk_fn: object = None

    # May the user answer "always" so it stops asking this session?
    trustable: bool = True

    def declaration(self):

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

    def describe(self, args):

        if self.preview is not None:
            return self.preview(args)

        details = ", ".join(f"{k}={v!r}" for k, v in args.items())

        return f"{self.name}({details})"


@dataclass
class ToolResult:
    ok: bool
    message: str
    needs_confirmation: bool = False


class ToolRegistry:

    def __init__(self, audit=None):

        self.tools = {}

        # Tools the user said "always" to, for this session only
        self.trusted = set()

        # Optional callable(name, args, result, confirmed) for the log
        self.audit = audit

    # ------------------------------------------------

    def register(self, tool):

        self.tools[tool.name] = tool

    def names(self):

        return list(self.tools)

    def declarations(self):

        return [tool.declaration() for tool in self.tools.values()]

    def safe_only(self):
        """
        A registry with just the SAFE-tier tools, for background work
        (routines) that must never ask or change anything.
        """

        view = ToolRegistry(audit=self.audit)

        for tool in self.tools.values():

            if tool.risk is Risk.SAFE and tool.risk_fn is None:
                view.register(tool)

        return view

    def trust(self, name):
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

    def execute(self, name, args, context, confirmed=False):
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

        try:

            outcome = tool.handler(context, **args)

        except Exception as e:

            log.exception("Tool %s failed", name)

            result = ToolResult(False, f"{tool.name} failed: {e}")

            self._audit(name, args, result, confirmed)

            return result

        if isinstance(outcome, tuple):
            ok, message = outcome
            result = ToolResult(bool(ok), str(message))

        else:
            result = ToolResult(True, str(outcome))

        self._audit(name, args, result, confirmed)

        return result

    # ------------------------------------------------

    def _audit(self, name, args, result, confirmed):

        if self.audit is None:
            return

        try:
            self.audit(name, args, result, confirmed)

        except Exception:
            log.exception("Audit log failed")

    def _ask_confirmation(self, tool, risk, args, context):

        prompt = tool.describe(args)

        if risk is Risk.DANGEROUS:
            prompt = f"Warning: {prompt}"

        context.pending_actions.start(
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
            if context.pending_actions.current().data["always"]
            else "Reply 'yes' to confirm or 'no' to cancel."
        )

        return ToolResult(True, f"{prompt}\n\n{options}", needs_confirmation=True)
