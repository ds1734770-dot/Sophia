class QueryClassifier:

    GENERIC_QUERIES = {
        "browser",
        "terminal",
        "music",
        "player",
        "editor",
        "coding",
        "code",
        "shell",
        "internet",
        "video",
        "mail",
        "email",
        "calculator",
        "notes",
        "office",
    }

    def is_semantic_query(self, query):

        query = query.lower().strip()

        return query in self.GENERIC_QUERIES