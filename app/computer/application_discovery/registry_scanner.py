try:
    import winreg
except ImportError:  # not on Windows
    winreg = None

from app.computer.application_discovery.executable_resolver import ExecutableResolver
from app.computer.application_normalizer import ApplicationNormalizer


class RegistryScanner:

    UNINSTALL_KEYS = [] if winreg is None else [

        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ),

        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),

        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ),

    ]

    def __init__(self):

        self.resolver = ExecutableResolver()
        self.normalizer = ApplicationNormalizer()

    def scan(self):

        applications = []

        if winreg is None:
            return applications

        for hive, path in self.UNINSTALL_KEYS:

            try:
                key = winreg.OpenKey(hive, path)

            except OSError:
                continue

            count = winreg.QueryInfoKey(key)[0]

            for i in range(count):

                try:

                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)

                    # -------------------------
                    # Display Name
                    # -------------------------

                    try:
                        name = winreg.QueryValueEx(
                            subkey,
                            "DisplayName",
                        )[0]
                    except Exception:
                        continue

                    # -------------------------
                    # Display Icon
                    # -------------------------

                    try:
                        icon = winreg.QueryValueEx(
                            subkey,
                            "DisplayIcon",
                        )[0]
                    except Exception:
                        icon = ""

                    # -------------------------
                    # Install Location
                    # -------------------------

                    try:
                        location = winreg.QueryValueEx(
                            subkey,
                            "InstallLocation",
                        )[0]
                    except Exception:
                        location = ""

                    # -------------------------
                    # Resolve Executable
                    # -------------------------

                    exe = self.resolver.resolve(
                        icon,
                        location,
                    )

                    # Skip entries that cannot be launched
                    if exe is None:
                        continue

                    applications.append(
                        {
                            "name": name,
                            "aliases": self.normalizer.aliases(name),
                            "exe": exe,
                            "type": "registry",
                        }
                    )

                except Exception:
                    continue

        return applications