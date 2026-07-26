from importlib.resources import path
import os
import subprocess
import ctypes
from pathlib import Path
from app.computer.windows_folders import WindowsFolders
from app.computer.explorer_window_manager import ExplorerWindowManager
from app.computer.windows_system_manager import WindowsSystemManager
from app.computer.application_manager import ApplicationManager


class ComputerManager:

    def __init__(self):

        self.explorer = ExplorerWindowManager()
        self.windows = WindowsSystemManager()
        self.app_manager = ApplicationManager()

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

    def close_app(self, app_name):

        app_name = app_name.lower().strip()

        aliases = {
            "vs code": "vscode",
            "visual studio code": "vscode",
        }

        app_name = aliases.get(app_name, app_name)

        if app_name not in self.APPS:
            return False, f"I don't know how to close '{app_name}'."

        process = self.APPS[app_name]["process"]

        try:

            subprocess.run(
                ["taskkill", "/IM", process, "/F"],
                check=True,
                capture_output=True,
            )

            return True, f"Closing {app_name.title()}..."

        except Exception:
            return False, f"{app_name.title()} isn't running."

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