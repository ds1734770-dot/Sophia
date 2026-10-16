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
from app.tools.undo import UndoStack
from app.tools.integration_tools import register_integration_tools
from app.tools.agent_tools import register_agent_tools
from app.agent.control import AgentControl
from app.agent.guard import ScreenGuard
from app.agent.observer import ScreenObserver
from app.agent.screen_agent import ScreenAgent, register_do_on_screen, register_skill_tools
from app.agent.skills import WhatsAppSkill
from app.tools.screen_agent_tools import build_screen_agent_registry
from app.config.settings import Settings
from app.tools.mcp_bridge import McpBridge
from app.tools.plugins import load_plugins
from app.computer.screen_control import ScreenControl
from app.computer.ui_automation import ScreenElements
from app.planner.reminder_service import FiredStore, RoutineStore, TimerStore



class _Mouse:
    """
    Clicks through the screen control, whose mouse backend is created
    only when it is first used.
    """

    def __init__(self, screen):
        self.screen = screen

    def click(self, x, y, button="left", double=False):
        self.screen.backend.click(x, y, button=button, double=double)

    def hotkey(self, *keys):
        self.screen.backend.hotkey(*keys)


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

        self.planner = ScheduleManager()
        self.timers = TimerStore(DATA_DIR / "timers.json")
        self.routines = RoutineStore(DATA_DIR / "routines.json")
        self.fired = FiredStore(DATA_DIR / "fired.json")

        self.undo = UndoStack()

        settings = Settings()

        # Does looking at the screen need a yes first? (menu setting) And how
        # much may she do on the screen without asking? ("auto": a whole task)
        self.screen_policy = {"confirm": False, "autonomy": settings.screen_autonomy}

        # the places she never touches, and the leash for a screen task
        self.screen_guard = ScreenGuard(settings.screen_blocked)
        self.screen_control = AgentControl(
            settings.screen_max_steps, settings.screen_max_seconds
        )

        self.screen = ScreenControl(
            capture_png=self.system_controls.capture_png,
            locate=self.chat_engine.client.locate_point,
            clipboard=self._clipboard(),
        )

        # Controls read from the Windows accessibility tree; the mouse
        # and keyboard are the screen's own, created when first needed
        self.elements = ScreenElements(
            mouse=_Mouse(self.screen),
            typer=self.screen.type_text,
        )

        self.registry = build_default_registry(
            computer=self.tool_engine.computer,
            browser=self.tool_engine.browser,
            files=self.file_manager,
            search=self.file_search,
            planner=self.planner,
            system=self.system_controls,
            vision=self.look_at_screen,
            shell=ShellRunner(),
            guard=self.guard,
            audit=AuditLog(LOGS_DIR / "actions.jsonl"),
            notes=NoteStore(DATA_DIR / "notes.json"),
            reminders=(self.timers, self.routines),
            screen=self.screen,
            elements=self.elements,
            screen_guard=self.screen_guard,
            undo=self.undo,
            screen_policy=self.screen_policy,
        )


        # Integrations: plugins (loaded now) and MCP servers (connected
        # in the background by start_integrations)
        self.plugins = load_plugins(
            self.registry,
            [DATA_DIR / "plugins", PROJECT_ROOT / "plugins"],
            services={"guard": self.guard, "data_dir": DATA_DIR},
        )

        self.mcp = McpBridge(self.registry, DATA_DIR / "mcp.json")

        from app.agents import get_hub

        register_agent_tools(self.registry, get_hub(), DATA_DIR)

        # The screen agent: a whole task on screen ("open WhatsApp and call X")
        self.screen_observer = ScreenObserver(self.elements)

        computer = self.tool_engine.computer

        agent_registry = build_screen_agent_registry(
            self.screen_observer,
            self.elements,
            self.screen,
            self.screen_guard,
            self.screen_control,
            open_app=lambda name: computer.open_app(name),
            focus_window=lambda title: computer.window_manager.window_action(title, "focus"),
            describe_screen=self.look_at_screen,
        )

        # its steps show up in the chat's live steps card and the action log
        agent_registry.observers = self.registry.observers
        agent_registry.audit = self.registry.audit

        self.screen_agent = ScreenAgent(
            self.chat_engine.client, self.screen_observer, agent_registry, self.screen_control
        )

        register_do_on_screen(self.registry, self.screen_agent, self.screen_policy)

        # common tasks done directly, with no AI request (and so no quota)
        self.whatsapp = WhatsAppSkill(
            self.screen_observer, self.elements, self.screen_control, self.screen_guard,
            open_app=lambda name: computer.open_app(name),
        )

        register_skill_tools(self.registry, self.whatsapp, self.screen_policy)

        register_integration_tools(
            self.registry, self.mcp, DATA_DIR / "mcp.json", self.plugins
        )

    def start_integrations(self):

        self.mcp.start()

    # -----------------------------------------------------

    def chat(self, conversation, system_instruction, context, on_text=None):
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
                on_text=on_text,
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

    @staticmethod
    def _clipboard():

        try:

            from app.tools.personal_tools import default_clipboard

            return default_clipboard()

        except Exception:
            return None

    def run_background(self, conversation, system_instruction, context):
        """
        Answer a prompt for a routine. Only read-only tools are
        available, and nothing can ask for confirmation.
        """

        context.registry = self.registry.safe_only()

        result = self.chat_engine.chat(
            conversation,
            system_instruction,
            registry=context.registry,
            context=context,
        )

        if not result["success"]:
            raise RuntimeError(result["response"])

        return result["response"]

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