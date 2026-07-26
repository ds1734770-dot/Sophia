from app.computer.application_indexer import ApplicationIndexer

apps = ApplicationIndexer().load()

for app in apps:
    if "trading" in app["name"].lower():
        print(app)