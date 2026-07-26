import os


class ApplicationLauncher:

    def launch(self, application):

        shortcut = application["shortcut"]

        try:

            os.startfile(shortcut)

            return (
                True,
                f"Opening {application['name']}..."
            )

        except Exception as e:

            return (
                False,
                str(e)
            )