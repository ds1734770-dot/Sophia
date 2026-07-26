from app.file.file_manager import FileManager
from app.file.file_indexer import FileIndexer


class FileEngine:

    def __init__(self):

        self.file_manager = FileManager()
        self.indexer = FileIndexer()

    def execute(self, command, context):

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

        # ----------------------------
        # Find Files
        # ----------------------------

        if command.lower().startswith("find "):

            query = command[5:].strip()

            if not query:

                return {
                    "handled": True,
                    "response": "Please specify what to search for."
                }

            success, results = self.indexer.search(query)

            if not success:

                return {
                    "handled": True,
                    "response": results,
                }

            response = []

            for file in results[:10]:

                response.append(
                    f"{file['type'].title()}: {file['name']}\n{file['path']}"
                )

            return {
                "handled": True,
                "response": "\n\n".join(response),
            }

        # ----------------------------
        # Rename
        # ----------------------------

        if command.lower().startswith("rename "):

            text = command[7:].strip()

            if " to " not in text:

                return {
                    "handled": True,
                    "response": "Usage: rename <old name> to <new name>"
                }

            old_name, new_name = text.split(" to ", 1)

            old_name = old_name.strip()
            new_name = new_name.strip()

            success, results = self.indexer.search(old_name)

            if not success:

                return {
                    "handled": True,
                    "response": results,
                }

            # Only one match -> rename immediately
            if len(results) == 1:

                success, response = self.file_manager.rename(
                    results[0]["path"],
                    new_name,
                )

                if success:
                    self.indexer.save()

                return {
                    "handled": True,
                    "response": response,
                }

            # Multiple matches -> create pending action

            context.pending_actions.start(

                action="rename",

                matches=results,

                data={
                    "new_name": new_name,
                }

            )

            message = "I found multiple matches:\n\n"

            for i, item in enumerate(results, start=1):

                message += (
                    f"{i}. {item['name']}\n"
                    f"   {item['path']}\n\n"
                )

            message += "Reply with the number of the item you want to rename."

            return {
                "handled": True,
                "response": message,
            }

        return {
            "handled": False,
            "response": None,
        }