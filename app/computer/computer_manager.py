from importlib.resources import path
import os
import subprocess
import ctypes
from pathlib import Path
from app.computer.windows_folders import WindowsFolders
from app.computer.explorer_window_manager import ExplorerWindowManager
from app.computer.windows_system_manager import WindowsSystemManager
from app.computer.application_manager import ApplicationManager
from app.computer.application_discovery.shortcut_resolver import ShortcutResolver
from app.computer.window_manager import WindowManager, process_name_for


class ComputerManager:

    def __init__(self):

        self.explorer = ExplorerWindowManager()
        self.windows = WindowsSystemManager()
        self.app_manager = ApplicationManager()
        self.window_manager = WindowManager()

    APPS = {
        "chrome": {
            "path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "process": "chrome.exe",
        },

        "vscode": {
            "path": r"C:\Users\%USERNAME%\AppData\Local\Programs\Microsoft VS Code\Code.exe",
            "process": "Code.exe",
        },

        "notepad": {
            "path": "notepad.exe",
            "process": "notepad.exe",
        },

        "cmd": {
            "path": "cmd.exe",
            "process": "cmd.exe",
        },

        "powershell": {
            "path": "powershell.exe",
            "process": "powershell.exe",
        },
    }

    # FOLDERS = {
    #         "downloads": WindowsFolders.get_folder("downloads"),
    #         "documents": WindowsFolders.get_folder("documents"),
    #         "desktop": WindowsFolders.get_folder("desktop"),
    #     }

    # -------------------------------------------------
    # Applications
    # -------------------------------------------------

    def open_app(self, app_name):

        app_name = app_name.lower().strip()
    
        aliases = {
            "vs code": "visual studio code",
            "vscode": "visual studio code",
        }
    
        app_name = aliases.get(app_name, app_name)
    
        return self.app_manager.open(app_name)

    ALIASES = {
        "vs code": "vscode",
        "visual studio code": "vscode",
    }

    def resolve_process(self, app_name):
        """
        The program file name to close for an app name, or None.
        Known apps first, then anything discovered on this PC.
        """

        app_name = app_name.lower().strip()
        app_name = self.ALIASES.get(app_name, app_name)

        if app_name in self.APPS:
            return self.APPS[app_name]["process"]

        application = self.app_manager.find(app_name)

        if application is None:
            return self.window_manager.guess_process(app_name)

        name = process_name_for(application)

        # Start Menu entries are shortcuts; the program is their target
        if name is None and application.get("shortcut"):

            info = ShortcutResolver().resolve(application["shortcut"])

            target = (info or {}).get("target") or ""

            if target.lower().endswith(".exe"):
                name = os.path.basename(target)

        # Store apps and the like: fall back to what is running now
        return name or self.window_manager.guess_process(app_name)

    def can_close(self, app_name):
        """
        True if Sophia can work out which program to close.
        """

        return self.resolve_process(app_name) is not None

    def close_app(self, app_name, force=False):

        process = self.resolve_process(app_name)

        if process is None:
            return False, f"I don't know how to close '{app_name}'."

        success, message = self.window_manager.close(process, force=force)

        if success:
            return True, f"Closing {app_name.title()}..."

        return False, message

    def window_action(self, name, action):

        return self.window_manager.window_action(name, action)

    # -------------------------------------------------
    # Folders
    # -------------------------------------------------

    def open_folder(self, folder_name):

        folder_name = folder_name.lower().strip()

        path = self.windows.get_folder(folder_name)

        if path is None:
            return False, f"I don't know the folder '{folder_name}'."

        try:
            os.startfile(path)
            return True, f"Opening {folder_name.title()}..."

        except Exception as e:
            return False, str(e)

    def close_folder(self, folder_name):

        folder_name = folder_name.lower().strip()

        path = self.windows.get_folder(folder_name)

        if path is None:
            return False, f"I don't know the folder '{folder_name}'."

        success = self.explorer.close_folder(path)

        if success:
            return True, f"Closing {folder_name.title()}..."

        return False, f"{folder_name.title()} isn't open."

    # -------------------------------------------------
    # Computer Controls
    # -------------------------------------------------

    def lock(self):

        try:

            ctypes.windll.user32.LockWorkStation()

            return True, "Locking computer..."

        except Exception as e:
            return False, str(e)