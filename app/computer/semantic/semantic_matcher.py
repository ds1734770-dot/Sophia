class SemanticMatcher:

    # ----------------------------------------

    def search(self, applications, query):

        query = query.lower().strip()

        matches = []

        for app in applications:

            tags = [
                tag.lower()
                for tag in app.get("tags", [])
            ]

            if query in tags:

                matches.append(app)

        return matches