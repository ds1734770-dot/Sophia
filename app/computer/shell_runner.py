"""
Runs PowerShell commands for the assistant.

Every command is shown to the user and confirmed first (see the tool
tiers). On top of that, some commands are refused outright and some are
flagged as dangerous.
"""

import re
import subprocess
from pathlib import Path

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
]


class ShellBlocked(Exception):
    """
    The command is refused; the message says why.
    """


def classify(command):
    """
    Returns "normal" or "dangerous"; raises ShellBlocked if refused.
    """

    text = command.lower()

    for pattern, reason in BLOCKED:

        if re.search(pattern, text):
            raise ShellBlocked(
                f"I won't run that: it involves {reason}. "
                "If you really need it, run it yourself in PowerShell."
            )

    for pattern in DANGEROUS:

        if re.search(pattern, text):
            return "dangerous"

    return "normal"


class ShellRunner:

    def __init__(self, run=None, cwd=None):

        self._run = run or subprocess.run
        self.cwd = str(cwd or Path.home())

    def run(self, command, timeout=DEFAULT_TIMEOUT):
        """
        Returns (ok, output). Output is trimmed; a timeout stops the
        command.
        """

        timeout = max(1, min(int(timeout), MAX_TIMEOUT))

        try:

            result = self._run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    command,
                ],
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
