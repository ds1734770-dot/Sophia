import json
import os


class MemoryStorage:

    FILE_NAME = "memory.json"

    @staticmethod
    def load():

        if not os.path.exists(MemoryStorage.FILE_NAME):
            return []

        with open(
            MemoryStorage.FILE_NAME,
            "r"
        ) as file:

            return json.load(file)

    @staticmethod
    def save(history):

        with open(
            MemoryStorage.FILE_NAME,
            "w"
        ) as file:

            json.dump(
                history,
                file,
                indent=4
            )