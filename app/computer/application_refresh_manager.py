from app.computer.application_refresh_result import ApplicationRefreshResult

from app.computer.application_discovery.fingerprint_manager import FingerprintManager
from app.computer.application_discovery.start_menu_scanner import StartMenuScanner
from app.computer.application_discovery.registry_scanner import RegistryScanner
from app.computer.application_discovery.desktop_scanner import DesktopScanner
from app.computer.application_discovery.chrome_pwa_scanner import ChromePWAScanner


class ApplicationRefreshManager:

    def __init__(self):

        self.fingerprint = FingerprintManager()

        self.start_menu = StartMenuScanner()
        self.registry = RegistryScanner()
        self.desktop = DesktopScanner()
        self.chrome = ChromePWAScanner()

    # ----------------------------------------------------

    def refresh(self):

        result = ApplicationRefreshResult()

        # -------------------------
        # Start Menu
        # -------------------------

        result.start_menu = self.start_menu.scan()

        if self.fingerprint.changed(
            "start_menu",
            result.start_menu
        ):
            result.changed = True

        # -------------------------
        # Registry
        # -------------------------

        result.registry = self.registry.scan()

        if self.fingerprint.changed(
            "registry",
            result.registry
        ):
            result.changed = True

        # -------------------------
        # Desktop
        # -------------------------

        result.desktop = self.desktop.scan()

        if self.fingerprint.changed(
            "desktop",
            result.desktop
        ):
            result.changed = True

        # -------------------------
        # Chrome PWAs
        # -------------------------

        result.chrome = self.chrome.scan()

        if self.fingerprint.changed(
            "chrome",
            result.chrome
        ):
            result.changed = True

        return result

    # ----------------------------------------------------

    def save_fingerprints(self, result):

        self.fingerprint.save(
            "start_menu",
            self.fingerprint.generate(result.start_menu)
        )

        self.fingerprint.save(
            "registry",
            self.fingerprint.generate(result.registry)
        )

        self.fingerprint.save(
            "desktop",
            self.fingerprint.generate(result.desktop)
        )

        self.fingerprint.save(
            "chrome",
            self.fingerprint.generate(result.chrome)
        )