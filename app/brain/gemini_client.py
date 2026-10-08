import time

from google import genai
from google.genai import types

from app.config.settings import Settings
from app.adapters.gemini_adapter import GeminiAdapter


class GeminiClient:

    MAX_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 1.5
    RETRYABLE_MARKERS = ("503", "UNAVAILABLE")

    # How many model <-> tool round trips one message may use
    MAX_TOOL_STEPS = 5

    def __init__(self):
        self.settings = Settings()

        self.client = genai.Client(
            api_key=self.settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=self.settings.request_timeout * 1000
            ),
        )

    # ------------------------------------------------

    def _call(self, contents, config):
        """
        One generate_content request, retrying temporary server errors.
        """

        for attempt in range(1, self.MAX_ATTEMPTS + 1):

            try:

                return self.client.models.generate_content(
                    model=self.settings.model_name,
                    contents=contents,
                    config=config,
                )

            except Exception as e:

                retryable = any(
                    marker in str(e)
                    for marker in self.RETRYABLE_MARKERS
                )

                if not retryable or attempt == self.MAX_ATTEMPTS:
                    raise

                time.sleep(self.RETRY_DELAY_SECONDS * attempt)

    @staticmethod
    def _system_text(conversation, system_instruction):

        system_text, turns = GeminiAdapter.split_system(conversation)

        parts = [p for p in (system_instruction, system_text) if p]

        return "\n\n".join(parts) or None, turns

    # ------------------------------------------------

    def generate(self, conversation, system_instruction):
        """
        Plain chat request.

        System messages in the conversation are merged with
        `system_instruction` and sent as the real system instruction.

        Returns the full Gemini response object.
        """

        system_text, turns = self._system_text(
            conversation, system_instruction
        )

        config = types.GenerateContentConfig(
            system_instruction=system_text
        )

        return self._call(GeminiAdapter.convert(turns), config)

    def generate_with_tools(
        self, conversation, system_instruction, registry, context
    ):
        """
        Chat request where Gemini may call Sophia's tools.

        Gemini only *asks* for a tool; the registry runs it, enforcing
        the safety tiers. A tool that needs the user's confirmation ends
        the loop and its question becomes the reply.

        Returns (reply_text, tool_was_used).
        """

        system_text, turns = self._system_text(
            conversation, system_instruction
        )

        config = types.GenerateContentConfig(
            system_instruction=system_text,
            tools=[types.Tool(function_declarations=registry.declarations())],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )

        contents = GeminiAdapter.convert(turns)

        used_tool = False

        for _ in range(self.MAX_TOOL_STEPS):

            response = self._call(contents, config)

            calls = response.function_calls

            if not calls:
                return response.text, used_tool

            used_tool = True

            # Keep the model's own turn (it may carry signatures Gemini
            # needs to see again).
            contents.append(response.candidates[0].content)

            results = []

            for call in calls:

                result = registry.execute(
                    call.name, call.args, context
                )

                if result.needs_confirmation:
                    return result.message, True

                results.append(
                    types.Part.from_function_response(
                        name=call.name,
                        response={
                            "ok": result.ok,
                            "result": result.message,
                        },
                    )
                )

            contents.append(types.Content(role="user", parts=results))

        return (
            "I couldn't finish that in a reasonable number of steps. "
            "Could you break it into smaller requests?",
            used_tool,
        )
