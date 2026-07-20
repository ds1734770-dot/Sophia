class MemoryExtractor:

    @staticmethod
    def extract(text):

        profile = {}

        text_lower = text.lower()

        if text_lower.startswith("my name is "):
            profile["name"] = text[11:].strip()

        elif text_lower.startswith("i am "):
            profile["name"] = text[5:].strip()

        return profile