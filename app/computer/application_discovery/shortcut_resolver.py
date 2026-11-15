class ShortcutResolver:
    """
    What a Windows .lnk shortcut points at. Returns None elsewhere.
    """

    def resolve(self, shortcut_path):

        try:

            import win32com.client

            shell = win32com.client.Dispatch("WScript.Shell")

            shortcut = shell.CreateShortcut(shortcut_path)

            return {

                "target": shortcut.TargetPath,

                "arguments": shortcut.Arguments,

                "working_directory": shortcut.WorkingDirectory,

                "icon": shortcut.IconLocation,

            }

        except Exception:

            return None
