from app.file.file_manager import FileManager
from app.file.file_indexer import FileIndexer


class FileEngine:
    """
    Local, no-AI shortcuts for exact file commands:

        create folder <name>
        find <name>
        rename <old name> to <new name>

    Anything that changes files goes through the tool registry, so the
    same safety checks and confirmations apply as for Gemini.
    """

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

            result = context.registry.execute(
                "create_folder",
                {"name": folder_name},
                context,
            )

            return {
                "handled": True,
                "response": result.message,
            }

        # ----------------------------
        # Find Files
        # ----------------------------

        if command.lower().startswith("find "):

            query = command[5:].strip()

            # "find the file I downloaded last week" is a sentence for
            # Gemini, not a file name.
            if len(query.split()) > 3:

                return {
                    "handled": False,
                    "response": None,
                }

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
        # Rename (single exact target only)
        # ----------------------------

        if command.lower().startswith("rename ") and " to " in command:

            old_name, new_name = command[7:].split(" to ", 1)

            success, results = self.indexer.search(old_name.strip())

            if not success:

                return {
                    "handled": True,
                    "response": results,
                }

            # Several matches: let Gemini ask which one is meant
            if len(results) != 1:

                return {
                    "handled": False,
                    "response": None,
                }

            result = context.registry.execute(
                "rename_file",
                {
                    "path": results[0]["path"],
                    "new_name": new_name.strip(),
                },
                context,
            )

            return {
                "handled": True,
                "response": result.message,
            }

        return {
            "handled": False,
            "response": None,
        }
