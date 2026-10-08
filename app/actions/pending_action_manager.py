from app.actions.pending_action import PendingAction


class PendingActionManager:

    def __init__(self):

        self.pending = PendingAction()

    def start(self, action, matches, data=None):

        self.pending.start(action, matches, data)

    def current(self):

        return self.pending

    def clear(self):

        self.pending.clear()