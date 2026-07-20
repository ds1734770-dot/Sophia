from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    def __init__(self):
        # Application
        self.app_name = os.getenv("APP_NAME")
        self.version = os.getenv("VERSION")
        self.debug = os.getenv("DEBUG")

        # AI
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("MODEL_NAME")