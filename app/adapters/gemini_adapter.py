from google.genai import types


class GeminiAdapter:

    @staticmethod
    def split_system(conversation):
        """
        Separate system messages from the chat turns.

        Returns (system_text, turns). Gemini takes system text through
        `system_instruction`, not as a user message.
        """

        system_parts = []
        turns = []

        for message in conversation:

            if message["role"] == "system":
                system_parts.append(message["content"])
            else:
                turns.append(message)

        return "\n\n".join(system_parts), turns

    @staticmethod
    def convert(conversation):
        """
        Convert Sophia's chat turns into Gemini's Content format.
        System messages are skipped; see split_system.
        """

        contents = []

        for message in conversation:

            if message["role"] == "system":
                continue

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
