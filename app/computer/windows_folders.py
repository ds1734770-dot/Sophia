from pathlib import Path

try:
    import winreg
except ImportError:  # not on Windows
    winreg = None


class WindowsFolders:

    @staticmethod
    def get_folder(name):

        if winreg is None:

            from app.computer.macos import get_folder

            return get_folder(name)

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
