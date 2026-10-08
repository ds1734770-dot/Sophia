"""
Facts shown to the user before a program is launched: is it digitally
signed, and was it downloaded from the internet?
"""

import json
import subprocess
from pathlib import Path

LAUNCHABLE = {".exe", ".lnk", ".msi", ".bat", ".cmd", ".com"}

# Never launched: scripts that run hidden code, registry files, libraries
NEVER_LAUNCHED = {".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".reg", ".dll", ".scr", ".jar"}


def from_internet(path):
    """
    True if Windows marked the file as downloaded (the Zone.Identifier
    stream), False if not, None if it cannot be checked.
    """

    try:

        with open(str(path) + ":Zone.Identifier", "r", encoding="utf-8", errors="ignore") as f:
            return "ZoneId=3" in f.read() or "ZoneId=4" in f.read()

    except FileNotFoundError:
        return False

    except OSError:
        return None


def signature(path, run=subprocess.run):
    """
    (status, publisher): status is "signed", "unsigned" or "unknown".
    """

    script = (
        "$s = Get-AuthenticodeSignature -LiteralPath $args[0]; "
        "@{status = [string]$s.Status; subject = [string]$s.SignerCertificate.Subject} | ConvertTo-Json -Compress"
    )

    try:

        result = run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script, str(path)],
            capture_output=True, text=True, timeout=10,
        )

        data = json.loads(result.stdout)

    except Exception:
        return "unknown", ""

    status = data.get("status", "")

    publisher = ""

    for part in (data.get("subject") or "").split(","):

        if part.strip().startswith("CN="):

            publisher = part.strip()[3:]

            break

    if status == "Valid":
        return "signed", publisher

    if status == "NotSigned":
        return "unsigned", ""

    return "unknown", publisher


def describe(path, sig=signature, internet=from_internet):
    """
    One line for the confirmation message.
    """

    path = Path(path)

    status, publisher = sig(path)

    parts = []

    if status == "signed":
        parts.append(f"signed by {publisher}" if publisher else "digitally signed")

    elif status == "unsigned":
        parts.append("NOT digitally signed")

    else:
        parts.append("signature could not be checked")

    downloaded = internet(path)

    if downloaded:
        parts.append("downloaded from the internet")

    return ", ".join(parts)
