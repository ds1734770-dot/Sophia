import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app.brain.tool_context import ToolContext
from app.computer.application_manager import ApplicationManager
from app.config.settings import Settings
from app.brain.brain import Brain
from app.brain.model_pool import UsageTracker
from app.settings.paths import USAGE_FILE

from app.memory.memory import Memory
from app.memory.memory_storage import MemoryStorage

from app.memory.user_profile import UserProfile
from app.memory.profile_storage import ProfileStorage

from app.memory.conversation_summary import ConversationSummary
from app.memory.summary_storage import SummaryStorage

from app.context.context_builder import ContextBuilder
from app.context.system_profile import system_profile
from app.computer.builtin_apps import merge_builtin

from app.memory.memory_filter import MemoryFilter
from app.memory.summarizer import Summarizer

from app.actions.pending_action_manager import PendingActionManager

from app.computer.background_watcher.watcher_manager import WatcherManager
from app.planner.reminder_service import ReminderService

log = logging.getLogger("sophia.core")


class Sophia:
    """
    The assistant. `respond()` handles one message and is used by every
    front end (console, desktop window, voice).
    """

    EXIT_WORDS = {"x", "exit", "quit", "bye"}

    def __init__(self):

        self.settings = Settings()
        self.brain = Brain()

        # One message at a time, whichever front end sent it
        self._turn_lock = threading.Lock()

        # Slow housekeeping (summaries, remembering facts) runs after the
        # reply is shown, one job at a time
        self._after_turn = ThreadPoolExecutor(max_workers=1, thread_name_prefix="after-turn")

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

        # Who to tell when a reminder, timer or routine fires
        self.notifier = None

        self.reminders = ReminderService(
            planner=self.brain.planner,
            timers=self.brain.timers,
            routines=self.brain.routines,
            fired=self.brain.fired,
            notify=self.notify,
            run_prompt=self.run_background_prompt,
        )

    # -----------------------------------------------------

    def start_services(self):
        """
        Start background work (keeps the app index current).
        """

        self.watcher_manager.start()
        self.reminders.start()
        self.brain.start_integrations()

    def start(self):

        print("=" * 50)
        print(f"{self.settings.app_name}")
        print(f"Version: {self.settings.version}")
        self.start_services()
        print("=" * 50)
        print("Sophia is online!")

    # -----------------------------------------------------

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

            log.warning("Memory extraction failed: %s", e)

    def _make_context(self, pending_actions):

        context = ToolContext()

        context.pending_actions = pending_actions
        context.memory = self.memory
        context.profile = self.profile
        context.settings = self.settings

        context.file_manager = self.brain.file_manager

        return context

    def _system_instruction(self):

        now = datetime.now().strftime("%A, %d %B %Y, %H:%M")

        text = (
            f"Current local date and time: {now}. "
            "The user is on Windows."
        )

        try:

            manager = self.brain.tool_engine.computer.app_manager

            text += "\n" + system_profile(
                lambda: merge_builtin(manager.indexer.load())
            )

        except Exception:
            log.debug("System profile unavailable", exc_info=True)

        return text

    def generate_response(self, on_text=None):
        """
        Build Sophia's complete context and generate a response.
        """

        conversation = ContextBuilder.build(
            profile=self.profile.get_all(),
            summary=self.summary.get(),
            history=self.memory.get_history()
        )

        options = {"on_text": on_text} if on_text is not None else {}

        return self.brain.chat(
            conversation=conversation,
            system_instruction=self._system_instruction(),
            context=self._make_context(self.pending_actions),
            **options,
        )

    # -----------------------------------------------------
    # Proactive features
    # -----------------------------------------------------

    def set_notifier(self, notifier):
        """
        notifier(title, text) is called from a background thread when a
        reminder, timer or routine fires.
        """

        self.notifier = notifier

    def notify(self, title, text):

        log.info("notify: %s: %s", title, text)

        if self.notifier is not None:

            self.notifier(title, text)

        else:

            print(f"\n[{title}] {text}")

    def run_background_prompt(self, prompt):
        """
        Run a routine's request. Separate from the chat: it does not
        touch the conversation or any pending confirmation.
        """

        conversation = ContextBuilder.build(
            profile=self.profile.get_all(),
            summary="",
            history=[{"role": "user", "content": prompt}],
        )

        return self.brain.run_background(
            conversation,
            self._system_instruction(),
            self._make_context(PendingActionManager()),
        )

    def _housekeeping(self, user_input, result):

        try:

            self.compact_history()

            # Only extract memory if NO tool was used
            if (not result["tool_used"]) and result["chat_success"]:
                self.update_profile(user_input)

        except Exception:
            log.exception("Housekeeping failed")

    def wait_idle(self, timeout=30):
        """
        Block until background housekeeping is done (for tests and exit).
        """

        done = threading.Event()

        self._after_turn.submit(done.set)

        done.wait(timeout)

    def process_assistant_response(self, response, compact=True):
        """
        Save Sophia's response.
        """

        self.memory.add(
            "assistant",
            response
        )

        if compact:
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

            if self.summarizer.maybe_summarize(
                self.memory, self.summary, lock=self._turn_lock
            ):

                SummaryStorage.save(self.summary.get())

        except Exception as e:

            log.warning("Summary failed: %s", e)

    def usage_report(self):
        """
        How many AI requests were made today, per model.
        """

        return UsageTracker(USAGE_FILE).report()

    # -----------------------------------------------------

    def respond(self, user_input, on_text=None):
        """
        Handle one user message. on_text(piece) is called with the
        answer as it is written, when it comes from Gemini.

        Returns {"response": str, "tool_used": bool}.
        """

        user_input = user_input.strip()

        if user_input.lower() == "usage":

            return {"response": self.usage_report(), "tool_used": True}

        with self._turn_lock:

            self.process_user_message(user_input)

            result = self.generate_response(on_text=on_text)

            log.info(
                "turn tool_used=%s chat_success=%s",
                result["tool_used"],
                result["chat_success"],
            )

            self.process_assistant_response(result["response"], compact=False)

        # Housekeeping can take as long as an AI request: the reply is
        # returned first and this runs in the background.
        self._after_turn.submit(self._housekeeping, user_input, result)

        return {
            "response": result["response"],
            "tool_used": result["tool_used"],
        }

    def chat(self):
        """
        Console loop.
        """

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

            result = self.respond(user_input)

            print(f"\n{self.settings.app_name}: {result['response']}")
