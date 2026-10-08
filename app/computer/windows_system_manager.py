import winreg
import os

class WindowsSystemManager:

    def __init__(self):

        self._folder_map = {
            "desktop": "Desktop",
            "documents": "Personal",
            "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
        }

    # --------------------------------

    def get_folder(self, name):

        name = name.lower()

        if name not in self._folder_map:
            return None

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        )

        value = winreg.QueryValueEx(
            key,
            self._folder_map[name]
        )[0]

        return os.path.expandvars(value)
