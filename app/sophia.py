from app.config.settings import Settings
from app.brain.brain import Brain

from app.memory.memory import Memory
from app.memory.memory_storage import MemoryStorage

from app.memory.user_profile import UserProfile
from app.memory.profile_storage import ProfileStorage

from app.memory.memory_extractor import MemoryExtractor

from app.context.context_builder import ContextBuilder


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

    def start(self):
        print("=" * 50)
        print(f"🤖 {self.settings.app_name}")
        print(f"Version: {self.settings.version}")
        print("=" * 50)
        print("Sophia is online!")

    def process_user_message(self, user_input):
        """
        Save the user's message and update long-term memory.
        """

        # Save conversation
        self.memory.add(
            "user",
            user_input
        )

        MemoryStorage.save(
            self.memory.get_history()
        )

        # Update long-term profile
        self.update_profile(user_input)

    def update_profile(self, user_input):
        """
        Extract important user facts and save them.

        NOTE:
        This currently uses the rule-based MemoryExtractor.
        Later we will replace it with:
            self.brain.extract_memory(user_input)
        """

        facts = MemoryExtractor.extract(user_input)

        for key, value in facts.items():
            self.profile.set(key, value)

        ProfileStorage.save(
            self.profile.get_all()
        )

    def generate_response(self):
        """
        Build Sophia's context and generate a response.
        """

        context = ContextBuilder.build(
            profile=self.profile.get_all(),
            history=self.memory.get_history()
        )

        response = self.brain.chat(
            conversation=context["conversation"],
            system_instruction=context["system_prompt"]
        )

        return response

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

            # Process user message
            self.process_user_message(user_input)

            # Generate response
            response = self.generate_response()

            # Save Sophia's response
            self.process_assistant_response(response)

            # Display response
            print(f"\n{self.settings.app_name}: {response}")