from google.genai import types


class GeminiAdapter:

    @staticmethod
    def convert(conversation):
        """
        Convert Sophia's conversation format into Gemini's Content format.
        """

        contents = []

        for message in conversation:

            role = "user"

            if message["role"] == "assistant":
                role = "model"

            contents.append(
                types.Content(
                    role=role,
                    parts=[
                        types.Part.from_text(
                            text=message["content"]
                        )
                    ]
                )
            )

        return contents