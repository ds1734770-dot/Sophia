

from app.brain.engines.chat_engine import ChatEngine
from app.brain.engines.memory_engine import MemoryEngine
from app.brain.engines.pending_action_engine import PendingActionEngine
from app.brain.engines.tool_engine import ToolEngine
from app.brain.brain_response import BrainResponse

class Brain:

    def __init__(self):

        self.chat_engine = ChatEngine()
        self.memory_engine = MemoryEngine()
        self.tool_engine = ToolEngine()
        self.pending_engine = PendingActionEngine()

    def chat(self, conversation, system_instruction, context):
        """
        Generate Sophia's reply.
        """
    
        try:
        
            last_message = conversation[-1]["content"]
    
            pending_result = self.pending_engine.process(
                last_message,
                context
            )

            if pending_result["handled"]:
                return pending_result

            tool_result = self.tool_engine.process(last_message,context)
    
            if tool_result["handled"]:

                return {
                    "response": tool_result["response"],
                    "tool_used": True,
                    "chat_success": False,
            }
    
            chat_result = self.chat_engine.chat(conversation,system_instruction)

            return {
                "response": chat_result["response"],
                "tool_used": False,
                "chat_success": chat_result["success"],
            }
                
        except Exception as e:

            return {
        "response": f"Error: {e}",
        "tool_used": False,
        "chat_success": False,
    }

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
    