from app.brain.gemini_client import GeminiClient


class ChatEngine:

    def __init__(self):
        self.client = GeminiClient()

    def chat(self, conversation, system_instruction):

        try:

            response = self.client.generate(
                conversation,
                system_instruction
            )

            return {
                "success": True,
                "response": response.text,
            }

        except Exception as e:

            error = str(e)

            # Quota exceeded
            if "429" in error or "RESOURCE_EXHAUSTED" in error:

                return {
                    "success": False,
                    "response": (
                        "I'm currently unable to answer AI questions because "
                        "the Gemini API quota has been reached.\n\n"
                        "I can still help with:\n"
                        "• Opening applications\n"
                        "• Browser control\n"
                        "• File management\n"
                        "• Time & date\n"
                        "• Calculator\n"
                        "• Computer control\n\n"
                        "Please try AI questions again later."
                    ),
                }

            # Server busy
            if "503" in error or "UNAVAILABLE" in error:

                return {
                    "success": False,
                    "response": (
                        "My AI service is temporarily busy. "
                        "Please try again in a few moments."
                    ),
                }

            # Anything else
            return {
                "success": False,
                "response": (
                    "Something went wrong while contacting my AI service."
                ),
            }