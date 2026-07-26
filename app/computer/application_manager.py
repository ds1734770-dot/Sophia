from app.computer.application_indexer import ApplicationIndexer
from app.computer.application_launcher import ApplicationLauncher


class ApplicationManager:

    def __init__(self):

        self.indexer = ApplicationIndexer()
        self.launcher = ApplicationLauncher()

    def open(self, app_name):

        app_name = app_name.lower().strip()

        applications = self.indexer.load()

        exact_matches = []
        alias_matches = []
        partial_matches = []

        # -----------------------
        # Exact Match
        # -----------------------

        for app in applications:

            if app["name"].lower() == app_name:

                exact_matches.append(app)

        if exact_matches:

            return self.launcher.launch(exact_matches[0])

        # -----------------------
        # Alias Match
        # -----------------------

        for app in applications:

            if app_name in app.get("aliases", []):

                alias_matches.append(app)

        if alias_matches:

            return self.launcher.launch(alias_matches[0])

        # -----------------------
        # Partial Match
        # -----------------------

        for app in applications:

            if app_name in app["name"].lower():

                partial_matches.append(app)

        if partial_matches:

            return self.launcher.launch(partial_matches[0])

        return False, "No matching application found."