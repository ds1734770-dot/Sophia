from app.actions.pending_action import PendingAction


class PendingActionManager:

    def __init__(self):

        self.pending = PendingAction()

    def start(self, action, matches, data=None):

        self.pending.action = action

        self.pending.matches = matches

        self.pending.data = data or {}

    def current(self):

        return self.pending

    def clear(self):

        self.pending.clear()