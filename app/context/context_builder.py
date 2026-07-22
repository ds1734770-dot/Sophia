from app.prompts.prompt_manager import PromptManager


class ContextBuilder:

    MAX_HISTORY = 15

    @staticmethod
    def build(profile, summary, history):
        """
        Build the complete context for Sophia.
        """

        conversation = []

        # System Prompt
        conversation.append({
            "role": "system",
            "content": PromptManager.chat_prompt()
        })

        # User Profile
        if profile:
            conversation.append({
                "role": "system",
                "content": f"User Profile:\n{profile}"
            })

        # Conversation Summary
        if summary:
            conversation.append({
                "role": "system",
                "content": f"Conversation Summary:\n{summary}"
            })

        # Only keep the most recent messages
        conversation.extend(
            history[-ContextBuilder.MAX_HISTORY:]
        )

        return conversation