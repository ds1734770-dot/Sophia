from app.brain.engines.calculator_engine import CalculatorEngine
from app.brain.engines.time_engine import TimeEngine
from app.brain.engines.computer_engine import ComputerEngine
from app.brain.engines.browser_engine import BrowserEngine
from app.brain.engines.quick_engine import QuickEngine


class ToolEngine:
    """
    The local fast path: a few exact commands answered instantly
    without any AI request. Anything unclear is left to Gemini, which
    decides what to do. When Gemini is unreachable, process_offline
    adds the fuzzy "open <app>" matching as a last resort.
    """

    def __init__(self):

        self.calculator = CalculatorEngine()
        self.time = TimeEngine()
        self.browser_engine = BrowserEngine()
        self.computer_engine = ComputerEngine()
        self.quick = QuickEngine()

        # Known websites come before app matching, so "open youtube"
        # opens the site instead of guessing an app.
        self.engines = [
            self.calculator,
            self.time,
            self.quick,
            self.browser_engine,
            self.computer_engine,
        ]

    @property
    def computer(self):
        return self.computer_engine.computer

    @property
    def browser(self):
        return self.browser_engine.browser

    def process(self, command, context):

        for engine in self.engines:

            result = engine.execute(command, context)

            if result["handled"]:
                return result

        return {
            "handled": False,
            "response": None,
        }

    def process_offline(self, command, context):
        """
        Used only when the AI is unavailable: allow fuzzy app matching
        and suggestions.
        """

        return self.computer_engine.execute(command, context, offline=True)
