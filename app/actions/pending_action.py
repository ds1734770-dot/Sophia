class PendingAction:

    def __init__(self):

        self.clear()

    def clear(self):

        self.action = None

        self.matches = []

        self.data = {}

    def exists(self):

        return self.action is not None