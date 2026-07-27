from app.computer.application_discovery.source_priority import SourcePriority
class DuplicateRemover:

    def remove(self, applications):

        best = {}

        for app in applications:

            name = app["name"].lower().strip()

            if name not in best:

                best[name] = app

                continue

            current = best[name]

            if SourcePriority.priority(app) > SourcePriority.priority(current):

                best[name] = app

        return list(best.values())