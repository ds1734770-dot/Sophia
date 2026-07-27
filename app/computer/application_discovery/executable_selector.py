from app.computer.application_discovery.executable_ranker import ExecutableRanker


class ExecutableSelector:

    def __init__(self):

        self.ranker = ExecutableRanker()

    def select(self, app_name, executables):

        return self.ranker.best(

            app_name,

            executables,

        )