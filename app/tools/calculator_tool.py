from app.tools.base_tool import BaseTool


class CalculatorTool(BaseTool):

    name = "calculator"

    description = "Evaluate mathematical expressions."

    def run(self, expression, **kwargs):

        try:
            return eval(
                expression,
                {"__builtins__": {}},
                {}
            )

        except Exception as e:
            return f"Calculation Error: {e}"