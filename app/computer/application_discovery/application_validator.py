from pathlib import Path


class ApplicationValidator:

    def validate(self, applications):

        valid = []

        for app in applications:

            app_type = app.get("type")

            if app_type == "shortcut":

                shortcut = Path(app["shortcut"])

                if shortcut.exists():
                    valid.append(app)

            else:

                valid.append(app)

        return valid