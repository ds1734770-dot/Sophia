"""
Tool registry: the single place where Sophia's abilities are declared
and where safety tiers are enforced.

Every action Sophia can take on the computer (whether Gemini asks for it
or a local command triggers it) goes through ToolRegistry.execute, so a
risky action can never skip its confirmation step.
"""

from dataclasses import dataclass, field
from enum import Enum

from google.genai import types


class Risk(Enum):
    # Runs immediately: read-only or easily undone
    SAFE = "safe"

    # Asks the user first: changes things, but can be undone
    CONFIRM = "confirm"

    # Always asks, with a clear warning: hard to undo
    DANGEROUS = "dangerous"


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

    def __init__(self):

        self.tools = {}

    # ------------------------------------------------

    def register(self, tool):

        self.tools[tool.name] = tool

    def names(self):

        return list(self.tools)

    def declarations(self):

        return [tool.declaration() for tool in self.tools.values()]

    # ------------------------------------------------

    def execute(self, name, args, context, confirmed=False):
        """
        Run a tool. Tools above the SAFE tier are held back as a pending
        confirmation unless `confirmed` is True.
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

        if tool.risk is not Risk.SAFE and not confirmed:

            return self._ask_confirmation(tool, args, context)

        try:

            outcome = tool.handler(context, **args)

        except Exception as e:

            return ToolResult(False, f"{tool.name} failed: {e}")

        if isinstance(outcome, tuple):
            ok, message = outcome
            return ToolResult(bool(ok), str(message))

        return ToolResult(True, str(outcome))

    # ------------------------------------------------

    def _ask_confirmation(self, tool, args, context):

        prompt = tool.describe(args)

        if tool.risk is Risk.DANGEROUS:
            prompt = f"Warning: {prompt}"

        context.pending_actions.start(
            action="confirm",
            matches=[],
            data={"tool": tool.name, "args": args},
        )

        return ToolResult(
            True,
            f"{prompt}\n\nReply 'yes' to confirm or 'no' to cancel.",
            needs_confirmation=True,
        )
