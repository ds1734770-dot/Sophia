"""
Runs shell commands for the assistant: PowerShell on Windows, zsh on
macOS.

Every command is shown to the user and confirmed first (see the tool
tiers). On top of that, some commands are refused outright and some are
flagged as dangerous.
"""

import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

IS_MAC = sys.platform == "darwin"

SHELL_NAME = "Terminal (zsh)" if IS_MAC else "PowerShell"

MAX_OUTPUT_CHARS = 4000
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120

# Never run these: they download-and-run code, hide commands, or weaken
# the machine's protection.
BLOCKED = [
    (r"\binvoke-expression\b|\biex\b", "running text as code"),
    (r"-enc(odedcommand)?\b", "encoded commands"),
    (r"downloadstring|downloadfile|start-bitstransfer", "downloading files to run"),
    (r"invoke-webrequest.*\|\s*(iex|invoke-expression)", "downloading and running code"),
    (r"set-mppreference|add-mppreference|disable-windowsoptionalfeature", "changing virus protection"),
    (r"set-executionpolicy", "changing script policy"),
    (r"\bnet\s+user\b|\bnet\s+localgroup\b", "changing user accounts"),
    (r"reg(\.exe)?\s+(add|delete|import)\s+hk(lm|ey_local_machine)", "editing system registry"),
    (r"\bformat-volume\b|\bformat\s+[a-z]:|\bdiskpart\b|\bclear-disk\b|\bbcdedit\b", "disk or boot changes"),
    (r"vssadmin\s+delete|wevtutil\s+cl", "deleting backups or logs"),
]

# macOS / Unix equivalents (checked on every system: harmless where
# they cannot run)
BLOCKED += [
    (r"(curl|wget)\b[^|;]*\|\s*(sudo\s+)?((ba|z|da|k)?sh|python3?|perl|ruby|osascript)\b", "downloading and running code"),
    (r"\bbase64\b[^|]*-d[^|]*\|\s*(ba|z)?sh\b|\beval\s+\"?\$\(", "running hidden code"),
    (r"\bsudo\b|\bsu\s+-?\s*\w*$|\bdoas\b", "administrator rights"),
    (r"\bcsrutil\b|\bspctl\s+--master-disable|\bspctl\s+--global-disable|\bfdesetup\b", "weakening the Mac's protection"),
    (r"\bdiskutil\s+(erase|zero|secureerase|partition|apfs\s+delete)|\bnewfs_|\bdd\s+if=", "disk changes"),
    (r"\bdscl\b|\bsysadminctl\b|\bdseditgroup\b", "changing user accounts"),
    (r"\btmutil\s+(delete|disable)|\blog\s+erase\b", "deleting backups or logs"),
    (r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$home)\s*($|;|&)", "deleting everything"),
    (r"\bsecurity\s+(find|dump|delete)-[\w-]*(password|keychain|certificate)", "reading saved passwords"),
]

# Allowed, but shown with a warning
DANGEROUS = [
    r"\bremove-item\b|\bdel\b|\berase\b|\brd\b|\brmdir\b|\brm\b",
    r"\bstop-process\b|\btaskkill\b|\bkill\b",
    r"\bstop-computer\b|\brestart-computer\b|\bshutdown\b",
    r"\bset-content\b|\bout-file\b|\badd-content\b|\s>>?\s*[\w\"'.\\/$]",
    r"\bmove-item\b|\brename-item\b|\bmv\b",
    r"\buninstall\b|\bmsiexec\b|\bwinget\s+(uninstall|install)\b|\bchoco\b",
    r"\bset-itemproperty\b|\bnew-itemproperty\b|\bremove-itemproperty\b",
    r"\bstop-service\b|\bset-service\b|\bdisable-\w+",
    r"\bnetsh\b|\bset-netfirewallrule\b|\bnew-netfirewallrule\b",
    r"\bkillall\b|\bpkill\b|\blaunchctl\b|\bhalt\b|\breboot\b|\bpmset\s+(?!-g\b)",
    r"\bdefaults\s+(write|delete)\b|\bchmod\b|\bchown\b|\bchflags\b|\bxattr\s+-[a-z]*[dc]",
    r"\bcp\b|\bln\b|\btouch\b|\bmkdir\b|\btee\b|\bsed\s+-i\b|\btruncate\b",
    r"\bbrew\s+(uninstall|remove|install|upgrade)\b|\bpip3?\s+(install|uninstall)\b|\bnpm\s+(i|install|uninstall)\b",
    r"\bnetworksetup\b|\bscutil\s+--set\b|\bsystemsetup\b|\bosascript\b",
]


class ShellBlocked(Exception):
    """
    The command is refused; the message says why.
    """


def classify(command: str) -> str:
    """
    Returns "normal" or "dangerous"; raises ShellBlocked if refused.
    """

    text = command.lower()

    for pattern, reason in BLOCKED:

        if re.search(pattern, text):
            raise ShellBlocked(
                f"I won't run that: it involves {reason}. "
                f"If you really need it, run it yourself in {'Terminal' if IS_MAC else 'PowerShell'}."
            )

    for pattern in DANGEROUS:

        if re.search(pattern, text):
            return "dangerous"

    return "normal"


class ShellRunner:

    def __init__(
        self,
        run: Callable[..., Any] | None = None,
        cwd: str | Path | None = None,
        mac: bool | None = None,
    ) -> None:

        self._run = run or subprocess.run
        self.cwd = str(cwd or Path.home())
        self.mac = IS_MAC if mac is None else mac

    def _command(self, command: str) -> list[str]:

        if self.mac:
            # -f: skip the user's startup files, like -NoProfile
            return ["/bin/zsh", "-f", "-c", command]

        return [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ]

    def run(self, command: str, timeout: int | float = DEFAULT_TIMEOUT) -> tuple[bool, str]:
        """
        Returns (ok, output). Output is trimmed; a timeout stops the
        command.
        """

        timeout = max(1, min(int(timeout), MAX_TIMEOUT))

        try:

            result = self._run(
                self._command(command),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.cwd,
                encoding="utf-8",
                errors="replace",
            )

        except subprocess.TimeoutExpired:

            return False, f"The command took longer than {timeout} seconds and was stopped."

        output = (result.stdout or "").strip()
        errors = (result.stderr or "").strip()

        if errors:
            output = f"{output}\n[errors]\n{errors}".strip()

        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n...(output cut)"

        if not output:
            output = "(no output)"

        return result.returncode == 0, output
