import json
import os
from app.settings.paths import PROFILE_FILE


class ProfileStorage:

    FILE_NAME = PROFILE_FILE

    @staticmethod
    def load():

        if not os.path.exists(ProfileStorage.FILE_NAME):
            return {}

        with open(ProfileStorage.FILE_NAME, "r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def save(profile):

        with open(ProfileStorage.FILE_NAME, "w", encoding="utf-8") as file:
            json.dump(profile, file, indent=4)