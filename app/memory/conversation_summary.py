class ConversationSummary:

    def __init__(self):
        self.summary = ""

    def get(self):
        return self.summary

    def set(self, summary):
        self.summary = summary

    def clear(self):
        self.summary = ""