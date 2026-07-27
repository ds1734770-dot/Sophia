import win32com.client


class ShortcutResolver:

    def resolve(self, shortcut_path):

        try:

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