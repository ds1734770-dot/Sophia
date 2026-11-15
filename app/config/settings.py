from dotenv import load_dotenv
import os
import sys

from app.config.secrets import get_stored_api_key

load_dotenv()

DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_TIMEOUT_SECONDS = 30

# Each model has its own free quota, so extra models are extra capacity.
DEFAULT_FALLBACK_MODELS = "gemini-3.8-flash,gemini-3.6-flash,gemini-3-flash-preview,gemini-3.1-flash-lite"

# Cheap model for background work (memory extraction, summaries).
DEFAULT_LIGHT_MODEL = "gemini-3.1-flash-lite"

# Local speech recognition (downloaded once on first use)
DEFAULT_WHISPER_MODEL = "base.en"

# Natural voice (Microsoft Edge neural voices; needs internet, falls back
# to the offline Windows voice) and the hands-free wake word
DEFAULT_TTS_VOICE = "en-IN-NeerjaNeural"
DEFAULT_WAKE_WORD = "hey_jarvis"


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
        self.tts_voice = os.getenv("TTS_VOICE") or DEFAULT_TTS_VOICE
        # Which voice speaks: "piper" (offline neural voice, the default),
        # "edge" (Microsoft's online neural voice) or "windows"
        self.tts_engine = (os.getenv("TTS_ENGINE") or "piper").strip().lower()
        # The screen agent. autonomy: "auto" (works through a task without
        # asking), "plan" or "ask" (confirm). SCREEN_BLOCKED adds window-title
        # words she must never touch (comma separated).
        self.screen_autonomy = (os.getenv("SCREEN_AUTONOMY") or "auto").strip().lower()
        self.screen_max_steps = int(os.getenv("SCREEN_MAX_STEPS") or 25)
        self.screen_max_seconds = int(os.getenv("SCREEN_MAX_SECONDS") or 180)
        self.screen_blocked = [
            w.strip() for w in (os.getenv("SCREEN_BLOCKED") or "").split(",") if w.strip()
        ]

        # Speech recognition: "moonshine" (fast: about 1 s for a command)
        # or "whisper" (about 2 s on a typical laptop). Whisper is also the
        # fallback if Moonshine cannot load.
        self.stt_engine = (os.getenv("STT_ENGINE") or "moonshine").strip().lower()
        self.moonshine_model = os.getenv("MOONSHINE_MODEL") or "base"

        # The small, quick model that double-checks a weak wake word match
        self.wake_check_model = os.getenv("WAKE_CHECK_MODEL") or "tiny.en"
        self.piper_voice = os.getenv("PIPER_VOICE") or "en_GB-jenny_dioco-medium"

        try:
            self.piper_speed = float(os.getenv("PIPER_SPEED") or 1.0)

        except ValueError:
            self.piper_speed = 1.0

        self.neural_voice = (os.getenv("NEURAL_VOICE") or "true").lower() not in ("0", "false", "no")
        self.wake_word = os.getenv("WAKE_WORD") or DEFAULT_WAKE_WORD
        self.wake_threshold = float(os.getenv("WAKE_THRESHOLD") or 0.5)
        # macOS refuses global shortcuts that use only Option, so the Mac
        # default is Ctrl+Option+H
        self.hide_hotkey = os.getenv("HIDE_HOTKEY") or (
            "ctrl+alt+h" if sys.platform == "darwin" else "alt+s"
        )

        # stops a screen task at once, from anywhere
        self.stop_hotkey = os.getenv("STOP_HOTKEY") or "ctrl+alt+x"
        self.sound_effects = (os.getenv("SOUND_EFFECTS") or "true").lower() not in ("0", "false", "no")
        self.sound_volume = float(os.getenv("SOUND_VOLUME") or 0.6)
        self.car_width = int(os.getenv("CAR_WIDTH") or 0) or None
        self.model_name = os.getenv("MODEL_NAME") or DEFAULT_MODEL
        self.fallback_models = [
            m.strip()
            for m in (
                os.getenv("FALLBACK_MODELS") or DEFAULT_FALLBACK_MODELS
            ).split(",")
            if m.strip()
        ]
        self.light_model = os.getenv("LIGHT_MODEL") or DEFAULT_LIGHT_MODEL
        # How hard the model thinks before answering: "minimal", "low",
        # "medium", "high", or "" to leave it to the model. Lower is faster.
        self.thinking_level = (os.getenv("THINKING_LEVEL") or "low").strip().lower()
        # Reports from other agents (Claude Code hooks, notify command)
        self.agent_hub = (os.getenv("AGENT_HUB") or "true").strip().lower() not in ("0", "false", "no", "off")
        self.agent_port = int(os.getenv("AGENT_PORT") or 47615)
        self.request_timeout = int(
            os.getenv("REQUEST_TIMEOUT") or DEFAULT_TIMEOUT_SECONDS
        )
