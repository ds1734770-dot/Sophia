import json
import os


class ProfileStorage:

    FILE_NAME = "profile.json"

    @staticmethod
    def load():

        if not os.path.exists(ProfileStorage.FILE_NAME):
            return {}

        with open(ProfileStorage.FILE_NAME, "r") as file:
            return json.load(file)

    @staticmethod
    def save(profile):

        with open(ProfileStorage.FILE_NAME, "w") as file:
            json.dump(profile, file, indent=4)