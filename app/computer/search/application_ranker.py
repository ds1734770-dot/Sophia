from app.computer.search.application_match import ApplicationMatch
from app.computer.search.scorer import Scorer
from app.computer.history.launch_history_manager import LaunchHistoryManager


class ApplicationRanker:

    def __init__(self):

        self.history = LaunchHistoryManager()

    # -------------------------------------------------

    def rank(self, applications, query):

        query = query.lower().strip()

        matches = []

        for app in applications:

            score = self._score(app, query)

            if score > 0:

                history_score = self.history.score(
                    app["name"]
                )

                # Give a maximum bonus of 30 points
                score += min(history_score, 30)

                matches.append(
                    ApplicationMatch(app, score)
                )

        matches.sort(
            key=lambda x: x.score,
            reverse=True
        )
        # for m in matches:
        #     print(m.app["name"], m.score)

        return matches

    # -------------------------------------------------

    def _score(self, app, query):

        name = app["name"].lower()

        aliases = [
            alias.lower()
            for alias in app.get("aliases", [])
        ]

        if name == query:
            return 1000

        if query in aliases:
            return 900

        if name.startswith(query):
            return 800

        if query in name:
            return 700

        score = Scorer.fuzzy(query, name)

        if score >= 60:
            return score

        return 0