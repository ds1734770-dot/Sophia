from google import genai
from google.genai import types

from app.config.settings import Settings
from app.adapters.gemini_adapter import GeminiAdapter


class GeminiClient:

    def __init__(self):
        self.settings = Settings()

        self.client = genai.Client(
            api_key=self.settings.gemini_api_key
        )

    def generate(self, conversation, system_instruction):
        """
        Sends a request to Gemini.

        Returns the full Gemini response object.
        """

        contents = GeminiAdapter.convert(conversation)

        config = types.GenerateContentConfig(
            system_instruction=system_instruction
        )

        response = self.client.models.generate_content(
            model=self.settings.model_name,
            contents=contents,
            config=config,
        )

        return response