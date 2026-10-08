class ToolContext:

    def __init__(self):

        self.pending_actions = None

        # Tool registry (safety tiers live here)
        self.registry = None

        self.memory = None

        self.profile = None

        self.settings = None

        # NEW
        self.file_manager = None

