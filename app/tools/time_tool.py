from datetime import datetime

from app.tools.base_tool import BaseTool


class TimeTool(BaseTool):

    name = "time"

    description = "Returns the current system time."

    def run(self, **kwargs):

        return datetime.now().strftime(
            "%I:%M:%S %p"
        )