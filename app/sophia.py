from multiprocessing import context

from app.brain.tool_context import ToolContext
from app.config.settings import Settings
from app.brain.brain import Brain

from app.memory.memory import Memory
from app.memory.memory_storage import MemoryStorage

from app.memory.user_profile import UserProfile
from app.memory.profile_storage import ProfileStorage

from app.memory.conversation_summary import ConversationSummary
from app.memory.summary_storage import SummaryStorage

from app.context.context_builder import ContextBuilder

from app.memory.memory_filter import MemoryFilter

from app.actions.pending_action_manager import PendingActionManager

class Sophia:

    def __init__(self):

        self.settings = Settings()
        self.brain = Brain()

        # Conversation Memory
        self.memory = Memory()
        self.memory.load(
            MemoryStorage.load()
        )

        # Long-Term User Profile
        self.profile = UserProfile()
        self.profile.load(
            ProfileStorage.load()
        )

        # Conversation Summary
        self.summary = ConversationSummary()
        self.summary.set(
            SummaryStorage.load()
        )
        self.pending_actions = PendingActionManager()


    def start(self):

        print("=" * 50)
        print(f"🤖 {self.settings.app_name}")
        print(f"Version: {self.settings.version}")
        print("=" * 50)
        print("Sophia is online!")

    def process_user_message(self, user_input):
        """
        Save the user's message.
        """

        self.memory.add(
            "user",
            user_input
        )

        MemoryStorage.save(
            self.memory.get_history()
        )

    def update_profile(self, user_input):
        """
        Extract important user facts.
        This should NEVER interrupt Sophia.
        """

        try:

            facts = self.brain.extract_memory(
                user_input
            )

            if not facts:
                return

            for key, value in facts.items():
                self.profile.set(
                    key,
                    value
                )

            ProfileStorage.save(
                self.profile.get_all()
            )

        except Exception as e:

            print(f"[Memory] {e}")

    def generate_response(self):
        """
        Build Sophia's complete context and generate a response.
        """

        conversation = ContextBuilder.build(
            profile=self.profile.get_all(),
            summary=self.summary.get(),
            history=self.memory.get_history()
        )

        context = ToolContext()

        context.pending_actions = self.pending_actions
        context.memory = self.memory
        context.profile = self.profile
        context.settings = self.settings

        context.file_manager = self.brain.tool_engine.engines[-1].file_manager
        context.file_indexer = self.brain.tool_engine.engines[-1].indexer
        
        return self.brain.chat(
            conversation=conversation,
            system_instruction="",
            context=context
        )

    def process_assistant_response(self, response):
        """
        Save Sophia's response.
        """

        self.memory.add(
            "assistant",
            response
        )

        MemoryStorage.save(
            self.memory.get_history()
        )

    def chat(self):

        while True:

            user_input = input("\nYou: ")

            if user_input.lower() in ["exit", "quit"]:

                print(f"\n{self.settings.app_name}: Goodbye! 👋")

                break

            # Save user message
            self.process_user_message(
                user_input
            )

            # Generate response
            result = self.generate_response()

            response = result["response"]
            
            tool_used = result["tool_used"]
            
            print(f"\n{self.settings.app_name}: {response}")
            
            self.process_assistant_response(response)
            
            # Only extract memory if NO tool was used
            if (not tool_used) and result["chat_success"]:
                self.update_profile(user_input)