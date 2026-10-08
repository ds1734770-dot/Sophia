class EntityParser:

    def parse(self, text):

        text = text.lower()

        for word in (

            "open",
            "launch",
            "start",
            "run",

            "please",
            "can",
            "could",
            "you",
            "my"

        ):

            text = text.replace(word, "")

        return text.strip()