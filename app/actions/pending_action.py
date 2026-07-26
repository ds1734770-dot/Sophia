class PendingAction:

    def __init__(self):

        self.action = None

        self.matches = []

        self.data = {}

        self.active = False

    def start(self, action, matches, data=None):

        self.action = action

        self.matches = matches

        self.data = data or {}

        self.active = True

    def clear(self):

        self.action = None

        self.matches = []

        self.data = {}

        self.active = False

    def exists(self):

        return self.active