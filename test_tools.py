from app.tools.tool_manager import ToolManager

manager = ToolManager()

print(manager.execute(
    "calculator",
    expression="12*(5+8)"
))

print(manager.execute("time"))