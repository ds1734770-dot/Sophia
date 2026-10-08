import json
import os
from app.settings.paths import MEMORY_FILE


class MemoryStorage:

    FILE_NAME = MEMORY_FILE

    # Keep the saved history bounded
    MAX_SAVED = 200

    @staticmethod
    def load():

        if not os.path.exists(MemoryStorage.FILE_NAME):
            return []

        with open(
            MemoryStorage.FILE_NAME,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    @staticmethod
    def save(history):

        with open(
            MemoryStorage.FILE_NAME,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                history[-MemoryStorage.MAX_SAVED:],
                file,
                indent=4
            )