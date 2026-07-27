from app.computer.application_discovery.start_menu_scanner import StartMenuScanner
from app.computer.application_discovery.registry_scanner import RegistryScanner
from app.computer.application_discovery.desktop_scanner import DesktopScanner
from app.computer.application_discovery.chrome_pwa_scanner import ChromePWAScanner
from app.computer.application_discovery.duplicate_remover import DuplicateRemover
from app.computer.application_discovery.application_validator import ApplicationValidator


class DiscoveryManager:

    def __init__(self):

        self.start_menu = StartMenuScanner()
        self.registry = RegistryScanner()
        self.desktop = DesktopScanner()
        self.chrome = ChromePWAScanner()

        self.duplicate_remover = DuplicateRemover()
        self.validator = ApplicationValidator()

    # -------------------------------------------------

    def discover(self):

        applications = []

        # Start Menu
        applications.extend(
            self.start_menu.scan()
        )

        # Registry
        applications.extend(
            self.registry.scan()
        )

        # Desktop
        applications.extend(
            self.desktop.scan()
        )

        # Chrome PWAs
        applications.extend(
            self.chrome.scan()
        )

        # Remove duplicates
        applications = self.duplicate_remover.remove(
            applications
        )

        # Validate applications
        applications = self.validator.validate(
            applications
        )

        print(
            f"[DiscoveryManager] Discovered {len(applications)} applications."
        )

        return applications