class UserProfile:

    def __init__(self):
        self.profile = {}

    def set(self, key: str, value):
        self.profile[key] = value

    def get(self, key: str):
        return self.profile.get(key)

    def get_all(self):
        return self.profile

    def load(self, data):
        self.profile = data

    def clear(self):
        self.profile.clear()