from app.brain.engines.chat_engine import ChatEngine
from app.brain.engines.memory_engine import MemoryEngine


class Brain:

    def __init__(self):

        self.chat_engine = ChatEngine()
        self.memory_engine = MemoryEngine()

    def chat(self, conversation, system_instruction):
        """
        Generate Sophia's reply.
        """

        try:
            return self.chat_engine.chat(
                conversation,
                system_instruction
            )

        except Exception as e:
            return f"Error: {e}"

    def extract_memory(self, user_message):
        """
        Extract long-term user information.
        """

        try:
            return self.memory_engine.extract(
                user_message
            )

        except Exception as e:
            print(f"Memory Extraction Error: {e}")
            return {}