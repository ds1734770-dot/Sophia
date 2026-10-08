from app.brain.engines.chat_engine import ChatEngine
from app.brain.engines.memory_engine import MemoryEngine
from app.brain.engines.pending_action_engine import PendingActionEngine
from app.brain.engines.tool_engine import ToolEngine
from app.planner.schedule_manager import ScheduleManager
from app.prompts.prompt_manager import PromptManager
from app.computer.system_controls import SystemControls
from app.tools.builtin_tools import build_default_registry
from app.tools.audit import AuditLog
from app.file.file_manager import FileManager
from app.file.path_guard import PathGuard
from app.file.search import FileSearch
from app.computer.shell_runner import ShellRunner
from app.settings.paths import DATA_DIR, LOGS_DIR, PROJECT_ROOT
from app.tools.notes_store import NoteStore



SUMMARY_MAX_MESSAGES = 60
SUMMARY_MAX_CHARS = 600


class Brain:

    def __init__(self):

        self.chat_engine = ChatEngine()
        self.memory_engine = MemoryEngine()
        self.tool_engine = ToolEngine()
        self.pending_engine = PendingActionEngine()

        # Every action goes through this registry, which enforces
        # the safety tiers for both local commands and Gemini.
        self.system_controls = SystemControls()

        # Sophia may not change her own folder
        self.guard = PathGuard(protected=[PROJECT_ROOT])
        self.file_manager = FileManager()
        self.file_search = FileSearch(self.guard)

        self.registry = build_default_registry(
            computer=self.tool_engine.computer,
            browser=self.tool_engine.browser,
            files=self.file_manager,
            search=self.file_search,
            planner=ScheduleManager(),
            system=self.system_controls,
            vision=self.look_at_screen,
            shell=ShellRunner(),
            guard=self.guard,
            audit=AuditLog(LOGS_DIR / "actions.jsonl"),
            notes=NoteStore(DATA_DIR / "notes.json"),
        )


    # -----------------------------------------------------

    def chat(self, conversation, system_instruction, context):
        """
        Generate Sophia's reply.
        """

        try:

            # Original user message
            last_message = conversation[-1]["content"]

            context.registry = self.registry

            # -----------------------------------------
            # Intent Processing
            # -----------------------------------------

            

            # -----------------------------------------
            # Pending Actions
            # -----------------------------------------

            pending_result = self.pending_engine.process(
                last_message,
                context
            )

            if pending_result["handled"]:

                return {
                    "response": pending_result["response"],
                    "tool_used": True,
                    "chat_success": False,
                }

            # -----------------------------------------
            # Tool Engine
            # -----------------------------------------

            tool_result = self.tool_engine.process(
                last_message,
                context
            )

            if tool_result["handled"]:

                return {
                    "response": tool_result["response"],
                    "tool_used": True,
                    "chat_success": False,
                }

            # -----------------------------------------
            # AI Chat
            # -----------------------------------------

            chat_result = self.chat_engine.chat(
                conversation,
                system_instruction,
                registry=self.registry,
                context=context,
            )

            if not chat_result["success"]:

                # The AI is unreachable: simple commands can still work
                offline_result = self.tool_engine.process_offline(
                    last_message,
                    context
                )

                if offline_result["handled"]:

                    return {
                        "response": offline_result["response"],
                        "tool_used": True,
                        "chat_success": False,
                    }

            return {
                "response": chat_result["response"],
                "tool_used": chat_result.get("tool_used", False),
                "chat_success": chat_result["success"],
            }

        except Exception as e:

            return {
                "response": f"Error: {e}",
                "tool_used": False,
                "chat_success": False,
            }

    # -----------------------------------------------------

    def look_at_screen(self, question):
        """
        Screenshot + question to Gemini. The image is never saved.
        """

        image = self.system_controls.capture_png()

        return self.chat_engine.client.describe_image(question, image)

    def summarize(self, previous_summary, messages):
        """
        Fold older messages into the running summary (background work,
        so it uses the cheap model).
        """

        # Bound the request: a long backlog is trimmed to its newest
        # messages, each cut short.
        messages = messages[-SUMMARY_MAX_MESSAGES:]

        transcript = "\n".join(
            f"{m['role']}: {m['content'][:SUMMARY_MAX_CHARS]}"
            for m in messages
        )

        request = (
            f"Previous summary:\n{previous_summary or '(none)'}\n\n"
            f"New messages:\n{transcript}"
        )

        response = self.chat_engine.client.generate(
            [{"role": "user", "content": request}],
            PromptManager.summary_prompt(),
            light=True,
        )

        return response.text

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