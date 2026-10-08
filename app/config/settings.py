from dotenv import load_dotenv
import os

from app.config.secrets import get_stored_api_key

load_dotenv()

DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_TIMEOUT_SECONDS = 30

# Each model has its own free quota, so extra models are extra capacity.
DEFAULT_FALLBACK_MODELS = "gemini-3-flash-preview,gemini-3.1-flash-lite"

# Cheap model for background work (memory extraction, summaries).
DEFAULT_LIGHT_MODEL = "gemini-3.1-flash-lite"

# Local speech recognition (downloaded once on first use)
DEFAULT_WHISPER_MODEL = "base.en"


class Settings:
    def __init__(self):
        # Application
        self.app_name = os.getenv("APP_NAME") or "Sophia"
        self.version = os.getenv("VERSION") or "0.1.0"
        self.debug = (os.getenv("DEBUG") or "").lower() in ("1", "true", "yes")

        # AI
        self.gemini_api_key = (
            os.getenv("GEMINI_API_KEY") or get_stored_api_key()
        )
        self.whisper_model = os.getenv("WHISPER_MODEL") or DEFAULT_WHISPER_MODEL
        self.model_name = os.getenv("MODEL_NAME") or DEFAULT_MODEL
        self.fallback_models = [
            m.strip()
            for m in (
                os.getenv("FALLBACK_MODELS") or DEFAULT_FALLBACK_MODELS
            ).split(",")
            if m.strip()
        ]
        self.light_model = os.getenv("LIGHT_MODEL") or DEFAULT_LIGHT_MODEL
        self.request_timeout = int(
            os.getenv("REQUEST_TIMEOUT") or DEFAULT_TIMEOUT_SECONDS
        )
