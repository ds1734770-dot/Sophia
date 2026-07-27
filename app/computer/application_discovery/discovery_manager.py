from app.computer.application_discovery.duplicate_remover import DuplicateRemover
from app.computer.application_discovery.application_validator import ApplicationValidator


class DiscoveryManager:

    def __init__(self):

        self.duplicate_remover = DuplicateRemover()
        self.validator = ApplicationValidator()

    # -------------------------------------------------

    def discover(self, refresh_result):

        applications = []

        applications.extend(refresh_result.start_menu)
        applications.extend(refresh_result.registry)
        applications.extend(refresh_result.desktop)
        applications.extend(refresh_result.chrome)

        # Remove duplicates
        applications = self.duplicate_remover.remove(applications)

        # Validate
        applications = self.validator.validate(applications)

        print(
            f"[DiscoveryManager] Discovered {len(applications)} applications."
        )

        return applications