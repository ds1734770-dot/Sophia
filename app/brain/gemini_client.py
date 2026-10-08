import time

from google import genai
from google.genai import types

from app.config.settings import Settings
from app.adapters.gemini_adapter import GeminiAdapter


class GeminiClient:

    MAX_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 1.5
    RETRYABLE_MARKERS = ("503", "UNAVAILABLE")

    def __init__(self):
        self.settings = Settings()

        self.client = genai.Client(
            api_key=self.settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=self.settings.request_timeout * 1000
            ),
        )

    def generate(self, conversation, system_instruction):
        """
        Sends a request to Gemini.

        System messages in the conversation are merged with
        `system_instruction` and sent as the real system instruction.
        Temporary server errors are retried; the last error is raised.

        Returns the full Gemini response object.
        """

        system_text, turns = GeminiAdapter.split_system(conversation)

        system_parts = [p for p in (system_instruction, system_text) if p]

        config = types.GenerateContentConfig(
            system_instruction="\n\n".join(system_parts) or None
        )

        contents = GeminiAdapter.convert(turns)

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
