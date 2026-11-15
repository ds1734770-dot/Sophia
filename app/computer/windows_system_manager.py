import os

try:
    import winreg
except ImportError:  # not on Windows
    winreg = None


class WindowsSystemManager:
    """
    Where the everyday folders are (Desktop, Documents, Downloads).
    """

    def __init__(self):

        self._folder_map = {
            "desktop": "Desktop",
            "documents": "Personal",
            "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
        }

    # --------------------------------

    def get_folder(self, name):

        name = name.lower()

        if winreg is None:

            from app.computer.macos import get_folder

            return get_folder(name)

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
