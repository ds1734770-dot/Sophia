import threading

from app.computer.application_indexer import ApplicationIndexer
from app.computer.application_launcher import ApplicationLauncher
from app.computer.application_refresh_manager import ApplicationRefreshManager
from app.computer.builtin_apps import merge_builtin

from app.computer.search.application_ranker import ApplicationRanker
from app.computer.search.confidence_evaluator import ConfidenceEvaluator

from app.computer.semantic.semantic_index import SemanticIndex


class ApplicationManager:

    def __init__(self):

        self.indexer = ApplicationIndexer()
        self.launcher = ApplicationLauncher()
        self.refresh_manager = ApplicationRefreshManager()

        self.ranker = ApplicationRanker()
        self.confidence = ConfidenceEvaluator()

        self.semantic = SemanticIndex()

        # The background refresher and the chat thread share the index
        self._lock = threading.RLock()

    # ----------------------------------------------------

    def initialize(self):

        # First launch
        if not self.indexer.database.exists():

            self.refresh()
            return

        self.refresh_if_changed()

    # ----------------------------------------------------

    def refresh_if_changed(self, quiet=False):
        """
        Rescan for installed apps; rebuild the index only when
        something changed. Returns True if the index was rebuilt.
        """

        with self._lock:

            result = self.refresh_manager.refresh()

            if not result.changed:

                if not quiet:
                    print("[ApplicationManager] Using cached application database.")

                return False

            applications = self.indexer.build(result)

            self.indexer.save(applications)

            self.refresh_manager.save_fingerprints(result)

            if not quiet:
                print("[ApplicationManager] Applications refreshed.")

            return True

    def refresh(self):

        with self._lock:

            result = self.refresh_manager.refresh()

            applications = self.indexer.build(result)

            count = self.indexer.save(applications)

            self.refresh_manager.save_fingerprints(result)

            print(f"[ApplicationManager] Indexed {count} applications.")

    # ----------------------------------------------------

    def _rank(self, app_name):

        with self._lock:
            applications = merge_builtin(self.indexer.load())

        applications = self.semantic.build(applications)

        return self.ranker.rank(applications, app_name)

    def find(self, app_name):
        """
        The single application that clearly matches the name, or None.
        """

        matches = self._rank(app_name)

        if matches and self.confidence.confident(matches):
            return matches[0].app

        return None

    # ----------------------------------------------------

    # An exact name, alias or prefix scores at least this much;
    # fuzzy and semantic guesses score below it.
    STRICT_SCORE = 800

    def open(self, app_name, strict=False):

        matches = self._rank(app_name)

        if not matches:

            return False, "No matching application found."

        if strict and (
            matches[0].score < self.STRICT_SCORE
            or not self.confidence.confident(matches)
        ):

            return False, "No exact application match."

        # ----------------------------------------
        # Confidence Evaluation
        # ----------------------------------------

        if not self.confidence.confident(matches):

            suggestions = "\n".join(

                f"{i + 1}. {match.app['name']}"

                for i, match in enumerate(matches[:5])

            )

            return (

                False,

                "I couldn't confidently identify the application.\n\n"
                "Did you mean:\n\n"
                f"{suggestions}"

            )

        # ----------------------------------------

        best = matches[0]

        return self.launcher.launch(best.app)
