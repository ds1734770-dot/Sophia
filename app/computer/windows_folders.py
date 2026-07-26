from pathlib import Path
import winreg


class WindowsFolders:

    @staticmethod
    def get_folder(name):

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        )

        mapping = {
            "desktop": "Desktop",
            "documents": "Personal",
            "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
        }

        value = winreg.QueryValueEx(
            key,
            mapping[name]
        )[0]

        return str(Path(value).expanduser())