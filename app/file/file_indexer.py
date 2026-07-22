import json
from pathlib import Path
from app.settings.paths import FILE_DATABASE


class FileIndexer:

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

    def __init__(self):

        self.home = Path.home()

        self.database = FILE_DATABASE

        self.search_locations = [

            self.home / "Desktop",

            self.home / "Documents",

            self.home / "Downloads",

        ]

    # --------------------------------

    def build(self):

        files = []

        for root in self.search_locations:

            if not root.exists():
                continue

            for path in root.rglob("*"):

                if any(
                    folder in path.parts
                    for folder in self.IGNORE_FOLDERS
                ):
                    continue

                if (
                    path.is_file()
                    and path.suffix.lower()
                    in self.IGNORE_EXTENSIONS
                ):
                    continue

                files.append({

                    "name": path.name,

                    "path": str(path),

                    "type": (
                        "folder"
                        if path.is_dir()
                        else "file"
                    ),

                    "extension": (
                        path.suffix.lower()
                        if path.is_file()
                        else ""
                    )

                })

        return files

    # --------------------------------

    def save(self):

        files = self.build()

        # Create the data folder if it doesn't exist
        self.database.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(
            self.database,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                files,
                f,
                indent=4
            )

        return len(files)

    # --------------------------------

    def load(self):

        if not self.database.exists():
            return []

        with open(
            self.database,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)