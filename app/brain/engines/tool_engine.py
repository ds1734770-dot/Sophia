from app.brain.engines.calculator_engine import CalculatorEngine
from app.brain.engines.file_engine import FileEngine
from app.brain.engines.time_engine import TimeEngine
from app.brain.engines.computer_engine import ComputerEngine
from app.brain.engines.browser_engine import BrowserEngine


class ToolEngine:

    def __init__(self):

        self.engines = [

            CalculatorEngine(),

            TimeEngine(),

            ComputerEngine(),

            BrowserEngine(),

            FileEngine(),

        ]

    @property
    def computer(self):
        return self._find(ComputerEngine).computer

    @property
    def browser(self):
        return self._find(BrowserEngine).browser

    @property
    def file_manager(self):
        return self._find(FileEngine).file_manager

    @property
    def indexer(self):
        return self._find(FileEngine).indexer

    def _find(self, engine_type):

        return next(
            e for e in self.engines if isinstance(e, engine_type)
        )

    def process(self, command, context):

        for engine in self.engines:

            result = engine.execute(command, context)

            if result["handled"]:
                return result

        return {
            "handled": False,
            "response": None,
        }