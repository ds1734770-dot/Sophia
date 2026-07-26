from app.computer.application_indexer import ApplicationIndexer

indexer = ApplicationIndexer()

while True:

    query = input("Search: ")

    success, result = indexer.search(query)

    print(success)
    print(result)