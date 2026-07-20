import json

from google import genai
from google.genai import types

from app.config.settings import Settings
from app.adapters.gemini_adapter import GeminiAdapter


class Brain:

    def __init__(self):
        self.settings = Settings()

        self.client = genai.Client(
            api_key=self.settings.gemini_api_key
        )

    def _generate(self, conversation, system_instruction):
        """
        Internal helper for communicating with Gemini.
        """

        gemini_history = GeminiAdapter.convert(conversation)

        config = types.GenerateContentConfig(
            system_instruction=system_instruction
        )

        response = self.client.models.generate_content(
            model=self.settings.model_name,
            contents=gemini_history,
            config=config,
        )

        return response.text

    def chat(self, conversation, system_instruction):
        """
        Normal conversation with Sophia.
        """

        try:
            return self._generate(
                conversation,
                system_instruction
            )

        except Exception as e:
            return f"Error: {e}"

    def extract_memory(self, user_message):
        """
        Extract long-term memory.
        """

        pass