from datetime import datetime

from app.brain.tool_context import ToolContext
from app.computer.application_manager import ApplicationManager
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
from app.memory.summarizer import Summarizer
from app.brain.model_pool import UsageTracker
from app.settings.paths import USAGE_FILE

from app.actions.pending_action_manager import PendingActionManager
from app.computer.application_indexer import ApplicationIndexer

from app.computer.background_watcher.watcher_manager import WatcherManager

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
        self.summarizer = Summarizer(self.brain.summarize)
        self.pending_actions = PendingActionManager()
        self.application_manager = ApplicationManager()
        self.application_manager.initialize()
        self.watcher_manager = WatcherManager(self.application_manager)


    def start(self):

        print("=" * 50)
        print(f"🤖 {self.settings.app_name}")
        print(f"Version: {self.settings.version}")
        self.watcher_manager.start()
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

        # Saves an AI request for the many messages with no personal fact
        if not MemoryFilter.should_extract(user_input):
            return

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

        context.file_manager = self.brain.tool_engine.file_manager
        context.file_indexer = self.brain.tool_engine.indexer

        now = datetime.now().strftime("%A, %d %B %Y, %H:%M")

        return self.brain.chat(
            conversation=conversation,
            system_instruction=(
                f"Current local date and time: {now}. "
                "The user is on Windows."
            ),
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

        self.compact_history()

        MemoryStorage.save(
            self.memory.get_history()
        )

    def compact_history(self):
        """
        Fold old messages into the summary once the chat gets long.
        Never interrupts Sophia.
        """

        try:

            if self.summarizer.maybe_summarize(self.memory, self.summary):

                SummaryStorage.save(self.summary.get())

        except Exception as e:

            print(f"[Summary] {e}")

    EXIT_WORDS = {"x", "exit", "quit", "bye"}

    def usage_report(self):
        """
        How many AI requests were made today, per model.
        """

        return UsageTracker(USAGE_FILE).report()

    def chat(self):

        while True:

            try:
                user_input = input("\nYou: ").strip()

            except (EOFError, KeyboardInterrupt):
                user_input = "x"

            if not user_input:
                continue

            if user_input.lower() in self.EXIT_WORDS:

                print(f"\n{self.settings.app_name}: Goodbye!")

                break

            if user_input.lower() == "usage":

                print(f"\n{self.settings.app_name}: {self.usage_report()}")

                continue

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
