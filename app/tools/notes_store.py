"""
Notes and to-dos kept in data/notes.json.
"""

import json
from datetime import datetime


class NoteStore:

    def __init__(self, path):

        self.path = path

        self.data = self._load()

    # ------------------------------------------------

    def _load(self):

        try:

            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)

        except (OSError, ValueError):
            data = {}

        data.setdefault("notes", [])
        data.setdefault("todos", [])
        data.setdefault("next_id", 1)

        return data

    def _save(self):

        self.path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def _new_id(self):

        value = self.data["next_id"]
        self.data["next_id"] = value + 1

        return value

    @staticmethod
    def _now():

        return datetime.now().isoformat(timespec="minutes")

    # ------------------------------------------------
    # Notes
    # ------------------------------------------------

    def add_note(self, text):

        note = {"id": self._new_id(), "text": text.strip(), "created": self._now()}

        self.data["notes"].append(note)
        self._save()

        return note

    def notes(self, search=None):

        items = self.data["notes"]

        if search:

            words = search.lower().split()

            items = [n for n in items if all(w in n["text"].lower() for w in words)]

        return items

    def delete_note(self, note_id):

        before = len(self.data["notes"])

        self.data["notes"] = [n for n in self.data["notes"] if n["id"] != note_id]

        self._save()

        return len(self.data["notes"]) < before

    # ------------------------------------------------
    # To-dos
    # ------------------------------------------------

    def add_todo(self, text, due=None):

        todo = {
            "id": self._new_id(),
            "text": text.strip(),
            "done": False,
            "due": due,
            "created": self._now(),
        }

        self.data["todos"].append(todo)
        self._save()

        return todo

    def todos(self, include_done=False):

        return [
            t for t in self.data["todos"] if include_done or not t["done"]
        ]

    def find_todo(self, ident):
        """
        By id, or by words from its text (the open one that matches).
        Returns the todo, or None / "ambiguous".
        """

        if isinstance(ident, int) or str(ident).isdigit():

            ident = int(ident)

            return next((t for t in self.data["todos"] if t["id"] == ident), None)

        words = str(ident).lower().split()

        matches = [
            t for t in self.data["todos"]
            if not t["done"] and all(w in t["text"].lower() for w in words)
        ]

        if len(matches) == 1:
            return matches[0]

        return "ambiguous" if matches else None

    def complete_todo(self, todo):

        todo["done"] = True
        todo["completed"] = self._now()
        self._save()

    def delete_todo(self, todo_id):

        before = len(self.data["todos"])

        self.data["todos"] = [t for t in self.data["todos"] if t["id"] != todo_id]

        self._save()

        return len(self.data["todos"]) < before
