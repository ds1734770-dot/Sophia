import hashlib
import json

from app.settings.paths import APPLICATION_DATABASE


class FingerprintManager:

    def __init__(self):

        self.file = APPLICATION_DATABASE.parent / "fingerprints.json"

    # ----------------------------------

    def generate(self, applications):

        names = sorted(

            app["name"]

            for app in applications

        )

        data = json.dumps(names)

        return hashlib.sha256(
            data.encode()
        ).hexdigest()

    # ----------------------------------

    def load(self):

        if not self.file.exists():
            return {}

        with open(
            self.file,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    # ----------------------------------

    def save(self, source, fingerprint):

        data = self.load()

        data[source] = fingerprint

        with open(
            self.file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                indent=4
            )

    # ----------------------------------

    def changed(self, source, applications):

        current = self.generate(applications)

        saved = self.load()

        return saved.get(source) != current