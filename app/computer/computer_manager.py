import os
import subprocess
from pathlib import Path
import ctypes


class ComputerManager:

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

    FOLDERS = {
        "downloads": str(Path.home() / "Downloads"),

        "documents": str(Path.home() / "Documents"),

        "desktop": str(Path.home() / "Desktop"),
    }

    def open_app(self, app_name):

        app_name = app_name.lower().strip()

        aliases = {
            "vs code": "vscode",
            "visual studio code": "vscode",
        }

        app_name = aliases.get(app_name, app_name)

        if app_name not in self.APPS:
            return False, f"I don't know how to open '{app_name}'."

        path = os.path.expandvars(self.APPS[app_name]["path"])

        try:
            subprocess.Popen(path)
            return True, f"Opening {app_name.title()}..."
        except Exception as e:
            return False, str(e)

    def open_folder(self, folder_name):

        folder_name = folder_name.lower()

        if folder_name not in self.FOLDERS:
            return False, f"I don't know the folder '{folder_name}'."

        path = self.FOLDERS[folder_name]

        try:
            os.startfile(path)
            return True, f"Opening {folder_name.title()}..."
        except Exception as e:
            return False, str(e)
    
    def close_app(self, app_name):

        app_name = app_name.lower()

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

        except Exception as e:
            return False, str(e)
        
    def lock(self):
        """
        Lock the computer.
        """

        try:
            ctypes.windll.user32.LockWorkStation()

            return True, "Locking computer..."

        except Exception as e:
            return False, str(e)