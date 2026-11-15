"""
The places Sophia never touches, however autonomous she is: banking and
payment pages, password managers and password fields, Windows settings and
security, and her own windows. Checked before every action on the screen.
"""

import re

# Titles (lower case) that mark a banking or payment page
PAYMENT_WORDS = (
    "net banking", "netbanking", "internet banking", "online banking", "mobile banking",
    "paypal", "razorpay", "stripe", "paytm", "phonepe", "google pay", "gpay", "billdesk",
    "checkout", "secure payment", "payment gateway", "make a payment", "payment",
    "credit card", "debit card", "upi", "wallet",
    "hdfc", "icici", "axis bank", "kotak", "state bank", "sbi online", "yes bank", "bank",
)

PASSWORD_MANAGER_WORDS = (
    "bitwarden", "1password", "lastpass", "keepass", "dashlane", "nordpass", "roboform",
    "enpass", "proton pass", "password manager", "saved passwords",
)

# Programs that are Windows' own settings and security
SYSTEM_PROCESSES = {
    "systemsettings.exe", "securityhealthui.exe", "securityhealthsystray.exe", "consent.exe",
    "mmc.exe", "regedit.exe", "control.exe", "msconfig.exe", "gpedit.msc", "secpol.msc",
    "taskmgr.exe", "windowsdefender.exe", "wf.msc",
    # macOS (process names are app names)
    "system settings", "system preferences", "keychain access", "passwords",
    "activity monitor", "securityagent", "coreservicesuiagent", "screen time",
    "disk utility", "directory utility", "migration assistant", "boot camp assistant",
}

SYSTEM_TITLES = (
    "windows security", "windows defender", "control panel", "registry editor",
    "local security policy", "local group policy", "user account control", "windows firewall",
    "device manager", "computer management", "system configuration", "task manager",
)

# What a text box is for: never typed into
SENSITIVE_FIELD = re.compile(
    r"\b(pass(?:word|code|phrase)?|otp|one[- ]?time|verification code|security code|cvv|cvc|"
    r"card number|pin|secret|recovery code)\b",
    re.IGNORECASE,
)

OWN_TITLES = ("sophia",)


class ScreenGuard:
    """
    check_window(title, process) -> (allowed, reason)
    check_field(name, is_password) -> (allowed, reason)
    """

    def __init__(self, extra_blocked=()):

        self.extra = tuple(w.strip().lower() for w in extra_blocked if w.strip())

    def check_window(self, title, process=""):

        text = (title or "").strip().lower()
        process = (process or "").strip().lower()

        if text in OWN_TITLES:
            return False, "That is my own window; I leave it alone."

        if process in SYSTEM_PROCESSES or any(w in text for w in SYSTEM_TITLES) or (
            text == "settings" or text.startswith("settings -")
        ):
            return False, "That is a system settings or security window, which I never change."

        if any(w in text for w in PASSWORD_MANAGER_WORDS):
            return False, "That is a password manager, which I never touch."

        if any(w in text for w in PAYMENT_WORDS):
            return False, "That looks like a banking or payment page, which I never touch."

        if any(w in text for w in self.extra):
            return False, "That window is on your list of places I must not touch."

        return True, ""

    def check_field(self, name="", is_password=False):
        """
        May text be typed into this field?
        """

        if is_password:
            return False, "That is a password box; please type it yourself."

        if SENSITIVE_FIELD.search(name or ""):
            return False, f"'{name}' looks like a secret (password, code or card), so I won't type into it."

        return True, ""
