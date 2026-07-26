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

    def process(self, command, context):

        for engine in self.engines:

            result = engine.execute(command, context)

            if result["handled"]:
                return result

        return {
            "handled": False,
            "response": None,
        }