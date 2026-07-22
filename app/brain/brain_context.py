class BrainContext:

    def __init__(
        self,
        user_input,
        memory,
        profile,
    ):
        self.user_input = user_input
        self.memory = memory
        self.profile = profile