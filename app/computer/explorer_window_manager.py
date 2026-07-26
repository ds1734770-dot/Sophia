import os
import win32com.client
import win32gui


class ExplorerWindowManager:

    def list_windows(self):

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