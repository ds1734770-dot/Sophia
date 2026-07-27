from app.computer.search.application_match import ApplicationMatch
from app.computer.search.scorer import Scorer
from app.computer.history.launch_history_manager import LaunchHistoryManager
from app.computer.semantic.semantic_matcher import SemanticMatcher
from app.computer.search.query_classifier import QueryClassifier


class ApplicationRanker:

    def __init__(self):

        self.history = LaunchHistoryManager()
        self.semantic = SemanticMatcher()
        self.classifier = QueryClassifier()

    # -------------------------------------------------

    def rank(self, applications, query):

        query = query.lower().strip()
    
        if self.classifier.is_semantic_query(query):
        
            return self._semantic_rank(
                applications,
                query
            )
    
        return self._name_rank(
            applications,
            query
        )
    
    # -------------------------------------------------
    def _name_rank(self, applications, query):

        matches = []

        for app in applications:

            score = self._score(app, query)

            if score > 0:

                score += self.history.score(
                    app["name"]
                )

                matches.append(
                    ApplicationMatch(
                        app,
                        score
                    )
                )

        matches.sort(
            key=lambda x: x.score,
            reverse=True
        )

        return matches

    def _semantic_rank(self, applications, query):

        matches = []
    
        semantic_matches = self.semantic.search(
            applications,
            query
        )
    
        for app in semantic_matches:
        
            score = 650 + self.history.score(
                app["name"]
            )
    
            matches.append(
                ApplicationMatch(
                    app,
                    score
                )
            )
    
        matches.sort(
            key=lambda x: x.score,
            reverse=True
        )
    
        return matches

    def _score(self, app, query):

        name = app["name"].lower()

        aliases = [
            alias.lower()
            for alias in app.get("aliases", [])
        ]

        # Exact Match
        if name == query:
            return 1000

        # Alias Match
        if query in aliases:
            return 900

        # Starts With
        if name.startswith(query):
            return 800

        # Contains
        if query in name:
            return 700

        # Fuzzy
        score = Scorer.fuzzy(
            query,
            name
        )

        if score >= 60:
            return score

        return 0