from app.prompts.prompt_manager import PromptManager
from app.conversation.conversation_builder import ConversationBuilder


class ContextBuilder:

    @staticmethod
    def build(profile, history):

        conversation = ConversationBuilder.build(history)

        return {
            "system_prompt": PromptManager.chat_prompt(),
            "profile": profile,
            "conversation": conversation,
        }