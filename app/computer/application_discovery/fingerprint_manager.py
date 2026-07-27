import hashlib
import json
from pathlib import Path

from app.settings.paths import APPLICATION_DATABASE


class FingerprintManager:

    def __init__(self):

        self.file = APPLICATION_DATABASE.parent / "fingerprint.json"

    def generate(self, applications):

        names = sorted(

            app["name"]

            for app in applications

        )

        data = json.dumps(names)

        return hashlib.sha256(

            data.encode()

        ).hexdigest()

    def load(self):

        if not self.file.exists():

            return None

        with open(

            self.file,

            "r",

            encoding="utf-8",

        ) as f:

            return json.load(f)

    def save(self, fingerprint):

        with open(

            self.file,

            "w",

            encoding="utf-8",

        ) as f:

            json.dump(

                {

                    "fingerprint": fingerprint

                },

                f,

                indent=4,

            )

    def changed(self, applications):

        current = self.generate(applications)

        saved = self.load()

        if saved is None:

            return True

        return current != saved["fingerprint"]