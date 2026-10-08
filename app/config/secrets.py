"""
The API key lives in Windows Credential Manager (via keyring), not in a
file inside the project. A GEMINI_API_KEY environment variable or .env
entry still wins, which keeps development simple.
"""

import logging

log = logging.getLogger("sophia.config")

SERVICE = "Sophia"
KEY_NAME = "gemini_api_key"


def get_stored_api_key():

    try:

        import keyring

        return keyring.get_password(SERVICE, KEY_NAME)

    except Exception as e:

        log.warning("Could not read the stored API key: %s", e)

        return None


def store_api_key(key):
    """
    Save the key. Returns True on success.
    """

    try:

        import keyring

        keyring.set_password(SERVICE, KEY_NAME, key.strip())

        return True

    except Exception as e:

        log.warning("Could not store the API key: %s", e)

        return False
