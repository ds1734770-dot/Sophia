import json

from app.brain.gemini_client import GeminiClient
from app.prompts.prompt_manager import PromptManager


class MemoryEngine:

    def __init__(self):
        self.client = GeminiClient()

    def extract(self, user_message):
        """
        Extract structured memory using Gemini.
        """

        conversation = [
            {
                "role": "user",
                "content": user_message
            }
        ]

        response = self.client.generate(
            conversation,
            PromptManager.memory_prompt()
        )

        try:
            return json.loads(response.text)

        except Exception:
            return {}