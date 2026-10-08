from dotenv import load_dotenv
import os

load_dotenv()

DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_TIMEOUT_SECONDS = 30


class Settings:
    def __init__(self):
        # Application
        self.app_name = os.getenv("APP_NAME") or "Sophia"
        self.version = os.getenv("VERSION") or "0.1.0"
        self.debug = (os.getenv("DEBUG") or "").lower() in ("1", "true", "yes")

        # AI
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("MODEL_NAME") or DEFAULT_MODEL
        self.request_timeout = int(
            os.getenv("REQUEST_TIMEOUT") or DEFAULT_TIMEOUT_SECONDS
        )
