from app.computer.application_indexer import ApplicationIndexer
from app.computer.application_launcher import ApplicationLauncher
from app.computer.application_refresh_manager import ApplicationRefreshManager

from app.computer.search.application_ranker import ApplicationRanker
from app.computer.search.confidence_evaluator import ConfidenceEvaluator

from app.computer.semantic.semantic_index import SemanticIndex
from app.computer.builtin_apps import merge_builtin


class ApplicationManager:

    def __init__(self):

        self.indexer = ApplicationIndexer()
        self.launcher = ApplicationLauncher()
        self.refresh_manager = ApplicationRefreshManager()

        self.ranker = ApplicationRanker()
        self.confidence = ConfidenceEvaluator()

        self.semantic = SemanticIndex()

    # ----------------------------------------------------

    def initialize(self):

        # First launch
        if not self.indexer.database.exists():

            self.refresh()
            return

        result = self.refresh_manager.refresh()

        if result.changed:

            applications = self.indexer.build(result)

            self.indexer.save(applications)

            self.refresh_manager.save_fingerprints(result)

            print("[ApplicationManager] Applications refreshed.")

        else:

            print("[ApplicationManager] Using cached application database.")

    # ----------------------------------------------------

    def refresh(self):

        result = self.refresh_manager.refresh()

        applications = self.indexer.build(result)

        count = self.indexer.save(applications)

        self.refresh_manager.save_fingerprints(result)

        print(f"[ApplicationManager] Indexed {count} applications.")

    # ----------------------------------------------------

    def open(self, app_name):

        applications = merge_builtin(self.indexer.load())

        applications = self.semantic.build(applications)

        matches = self.ranker.rank(
            applications,
            app_name
        )

        if not matches:

            return False, "No matching application found."

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