from app.brain.gemini_client import GeminiClient


class ChatEngine:

    def __init__(self):
        self.client = GeminiClient()

    def chat(self, conversation, system_instruction):

        response = self.client.generate(
            conversation,
            system_instruction
        )

        return response.text