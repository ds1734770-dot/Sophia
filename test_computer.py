from app.file.file_indexer import FileIndexer

indexer = FileIndexer()

count = indexer.save()

print(f"Indexed {count} items.")

database = indexer.load()

print(database[:5])