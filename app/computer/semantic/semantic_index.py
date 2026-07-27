from app.computer.semantic.tag_generator import TagGenerator


class SemanticIndex:

    def __init__(self):

        self.generator = TagGenerator()

    # ----------------------------------------

    def build(self, applications):

        semantic_apps = []

        for app in applications:

            app = app.copy()

            app["tags"] = self.generator.generate(
                app["name"]
            )

            semantic_apps.append(app)

        return semantic_apps