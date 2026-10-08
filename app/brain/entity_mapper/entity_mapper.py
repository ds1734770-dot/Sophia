class EntityMapper:

    MAP = {

        # Browsing
        "browser": "browser",
        "internet": "browser",
        "web": "browser",
        "website": "browser",

        # Coding
        "coding": "vscode",
        "code": "vscode",
        "programming": "vscode",
        "editor": "vscode",
        "develop": "vscode",

        # Music
        "music": "spotify",
        "song": "spotify",
        "songs": "spotify",
        "audio": "spotify",

        # Terminal
        "terminal": "git bash",
        "shell": "git bash",
        "bash": "git bash",
        "command": "git bash",

    }

    # ----------------------------------------

    def map(self, entity):

        entity = entity.lower().strip()

        return self.MAP.get(entity, entity)