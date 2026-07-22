from app.tools.calculator_tool import CalculatorTool
from app.tools.time_tool import TimeTool


class ToolManager:

    def __init__(self):

        self.tools = {
            CalculatorTool.name: CalculatorTool(),
            TimeTool.name: TimeTool(),
        }

    def get_tool(self, name):

        return self.tools.get(name)

    def execute(self, name, **kwargs):

        tool = self.get_tool(name)

        if tool is None:
            return f"Tool '{name}' not found."

        return tool.run(**kwargs)

    def available_tools(self):

        return list(self.tools.keys())