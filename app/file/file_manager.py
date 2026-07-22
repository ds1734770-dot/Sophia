import os
import shutil
from pathlib import Path


class FileManager:

    IGNORE_FOLDERS = {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "Lib",
        "site-packages",
        "build",
        "dist",
    }

    IGNORE_EXTENSIONS = {
        ".pyc",
        ".pyo",
    }

    MAX_RESULTS = 15

    def __init__(self):

        self.home = Path.home()

    # ----------------------------
    # Create Folder
    # ----------------------------

    def create_folder(self, folder_name, location=None):

        try:

            if location is None:
                location = self.home / "Documents"

            else:
                location = Path(location)

            path = location / folder_name

            path.mkdir(
                parents=True,
                exist_ok=True
            )

            return True, f"Folder '{folder_name}' created."

        except Exception as e:
            return False, str(e)

    # ----------------------------
    # Rename
    # ----------------------------

    def rename(self, old_path, new_name):

        try:

            old_path = Path(old_path)

            new_path = old_path.parent / new_name

            old_path.rename(new_path)

            return True, f"Renamed to '{new_name}'."

        except Exception as e:
            return False, str(e)

    # ----------------------------
    # Move
    # ----------------------------

    def move(self, source, destination):

        try:

            shutil.move(source, destination)

            return True, "File moved successfully."

        except Exception as e:
            return False, str(e)

    # ----------------------------
    # Delete
    # ----------------------------

    def delete(self, path):

        try:

            path = Path(path)

            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

            return True, "Deleted successfully."

        except Exception as e:
            return False, str(e)

    # ----------------------------
    # Exists
    # ----------------------------

    def exists(self, path):

        return Path(path).exists()

    # ----------------------------
    # Open File
    # ----------------------------

    def open_file(self, path):

        try:

            path = Path(path)

            if not path.exists():
                return False, "File not found."

            os.startfile(path)

            return True, f"Opening '{path.name}'..."

        except Exception as e:
            return False, str(e)

    # ----------------------------
    # Search
    # ----------------------------

    def search(self, query):

        try:

            query = query.lower().strip()

            results = []

            search_locations = [

                self.home / "Desktop",
                self.home / "Documents",
                self.home / "Downloads",

            ]

            for root in search_locations:

                if not root.exists():
                    continue

                for path in root.rglob("*"):

                    # Ignore unwanted folders
                    if any(folder in path.parts for folder in self.IGNORE_FOLDERS):
                        continue

                    # Ignore unwanted file types
                    if (
                        path.is_file()
                        and path.suffix.lower() in self.IGNORE_EXTENSIONS
                    ):
                        continue

                    filename = path.name.lower()

                    if query not in filename:
                        continue

                    # ---------- Relevance Score ----------

                    score = 0

                    if filename == query:
                        score += 100

                    elif filename.startswith(query):
                        score += 75

                    elif query in filename:
                        score += 50

                    if path.parent == self.home / "Documents":
                        score += 10

                    results.append({

                        "score": score,

                        "name": path.name,

                        "path": str(path),

                        "type": "folder" if path.is_dir() else "file",

                        "extension": path.suffix.lower() if path.is_file() else "",

                    })

            if not results:
                return False, "No matching files found."

            # Sort by relevance
            results.sort(
                key=lambda item: item["score"],
                reverse=True
            )

            # Remove internal score before returning
            cleaned = []

            for item in results[:self.MAX_RESULTS]:

                item.pop("score")

                cleaned.append(item)

            return True, cleaned

        except Exception as e:
            return False, str(e)