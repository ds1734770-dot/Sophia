from app.brain.engines.calculator_engine import CalculatorEngine
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

        ]

    def process(self, command):

        for engine in self.engines:

            result = engine.execute(command)

            if result["handled"]:
                return result

        return {
            "handled": False,
            "response": None,
        }