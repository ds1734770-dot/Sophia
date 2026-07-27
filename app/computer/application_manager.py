from app.computer.application_indexer import ApplicationIndexer
from app.computer.application_launcher import ApplicationLauncher
from app.computer.application_refresh_manager import ApplicationRefreshManager


class ApplicationManager:

    def __init__(self):

        self.indexer = ApplicationIndexer()
        self.launcher = ApplicationLauncher()
        self.refresh_manager = ApplicationRefreshManager()

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

        app_name = app_name.lower().strip()

        applications = self.indexer.load()

        # Exact Match
        for app in applications:

            if app["name"].lower() == app_name:

                return self.launcher.launch(app)

        # Alias Match
        for app in applications:

            if app_name in app.get("aliases", []):

                return self.launcher.launch(app)

        # Partial Match
        for app in applications:

            if app_name in app["name"].lower():

                return self.launcher.launch(app)

        return False, "No matching application found."