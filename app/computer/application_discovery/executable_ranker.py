from pathlib import Path


class ExecutableRanker:

    BLACKLIST = {

        "uninstall",
        "setup",
        "update",
        "updater",
        "helper",
        "crash",
        "repair",
        "remove",
        "installer",

    }

    def score(self, app_name, executable):

        app = app_name.lower().strip()

        filename = Path(executable).stem.lower()

        score = 0

        # ---------------------------------------
        # Exact filename match
        # ---------------------------------------

        if filename == app:
            score += 100

        # ---------------------------------------
        # Filename contains app name
        # ---------------------------------------

        if app in filename:
            score += 80

        # ---------------------------------------
        # App name contains filename
        # ---------------------------------------

        if filename in app:
            score += 60

        # ---------------------------------------
        # Penalize bad executables
        # ---------------------------------------

        for word in self.BLACKLIST:

            if word in filename:
                score -= 100

        return score

    def best(self, app_name, executables):

        if not executables:
            return None

        ranked = sorted(

            executables,

            key=lambda exe: self.score(app_name, exe),

            reverse=True,

        )

        return ranked[0]