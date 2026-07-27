from app.computer.application_indexer import ApplicationIndexer
from app.computer.application_launcher import ApplicationLauncher
from app.computer.application_refresh_manager import ApplicationRefreshManager
from app.computer.search.application_ranker import ApplicationRanker
from app.computer.semantic.semantic_index import SemanticIndex


class ApplicationManager:

    def __init__(self):

        self.indexer = ApplicationIndexer()
        self.launcher = ApplicationLauncher()
        self.refresh_manager = ApplicationRefreshManager()
        self.ranker = ApplicationRanker()
        self.semantic = SemanticIndex()

    # -----------------------------------------

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

    # -----------------------------------------

    def refresh(self):

    # Scan computer once
        result = self.refresh_manager.refresh()

        # Merge + validate
        applications = self.indexer.build(result)

        # Save database
        count = self.indexer.save(applications)

        # Save fingerprints
        self.refresh_manager.save_fingerprints(result)

        print(f"[ApplicationManager] Indexed {count} applications.")

    # -----------------------------------------

    def open(self, app_name):

        applications = self.indexer.load()
        applications = self.semantic.build(applications)
    
        matches = self.ranker.rank(
            applications,
            app_name
        )
    
        if not matches:
        
            return False, "No matching application found."
    
        return self.launcher.launch(
            matches[0].app
        )