import os
import sys


class ExplorerWindowManager:
    """
    Open folder windows (File Explorer on Windows, Finder on macOS).
    """

    def list_windows(self):

        if sys.platform != "win32":
            return []

        import win32com.client

        shell = win32com.client.Dispatch("Shell.Application")

        windows = []

        for window in shell.Windows():

            try:

                path = os.path.normcase(
                    window.Document.Folder.Self.Path
                )

                hwnd = window.HWND

                windows.append({
                    "path": path,
                    "hwnd": hwnd,
                    "window": window,
                })

            except Exception:
                pass

        return windows

    # ------------------------------------

    def close_folder(self, folder_path):

        if sys.platform == "darwin":

            from app.computer.macos import close_finder_folder

            return close_finder_folder(folder_path)

        import win32gui

        folder_path = os.path.normcase(folder_path)

        for window in self.list_windows():

            if window["path"] == folder_path:

                win32gui.PostMessage(
                    window["hwnd"],
                    0x0010,          # WM_CLOSE
                    0,
                    0,
                )

                return True

        return False
