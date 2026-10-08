from app.tools.base_tool import BaseTool
from app.brain.engines.calculator_engine import safe_eval


class CalculatorTool(BaseTool):

    name = "calculator"

    description = "Evaluate mathematical expressions."

    def run(self, expression, **kwargs):

        try:
            return safe_eval(expression)

        except Exception as e:
            return f"Calculation Error: {e}"
