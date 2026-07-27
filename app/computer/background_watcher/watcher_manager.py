from app.computer.dirty_flags import DirtyFlags

from app.computer.background_watcher.registry_watcher import RegistryWatcher
from app.computer.background_watcher.desktop_watcher import DesktopWatcher
from app.computer.background_watcher.startmenu_watcher import StartMenuWatcher


class WatcherManager:

    def __init__(self):

        self.flags = DirtyFlags()

        self.registry = RegistryWatcher(self.flags)
        self.desktop = DesktopWatcher(self.flags)
        self.start_menu = StartMenuWatcher(self.flags)

    # --------------------------------------------

    def start(self):

        self.registry.start()

        self.desktop.start()

        self.start_menu.start()