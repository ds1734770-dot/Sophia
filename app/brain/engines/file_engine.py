from app.file.file_manager import FileManager
from app.file.file_indexer import FileIndexer


class FileEngine:

    def __init__(self):

        self.file_manager = FileManager()
        self.indexer = FileIndexer()

    def execute(self, command):


        command = command.strip()

        # ----------------------------
        # Create Folder
        # ----------------------------


        if command.lower().startswith("create folder"):
  

            folder_name = command[len("create folder"):].strip()

            if not folder_name:

                return {
                    "handled": True,
                    "response": "Please provide a folder name."
                }

            success, response = self.file_manager.create_folder(folder_name)

            if success:
                self.indexer.save()

            return {
                "handled": True,
                "response": response,
            }

        return {
            "handled": False,
            "response": None,
        }