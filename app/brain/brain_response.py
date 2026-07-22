class BrainResponse:

    def __init__(
        self,
        response="",
        source="chat",
        tool_used=None,
        memory_updated=False,
    ):
        self.response = response
        self.source = source
        self.tool_used = tool_used
        self.memory_updated = memory_updated