"""
Whole-PC file search.

Uses the Windows Search index (fast, covers every indexed drive). If the
index is unavailable it falls back to walking the user's folders.
"""

import logging
import os
import time
from pathlib import Path

log = logging.getLogger("sophia.files")

INDEX_FETCH = 80
WALK_SECONDS = 8


def windows_index_query(terms, limit):
    """
    Ask Windows Search for file names containing every term.
    Returns a list of full paths (newest first).
    """

    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()

    try:

        conditions = " AND ".join(
            "System.FileName LIKE '%{}%'".format(
                t.replace("'", "''").replace("[", "[[]")
            )
            for t in terms
        )

        sql = (
            f"SELECT TOP {int(limit)} System.ItemPathDisplay "
            f"FROM SystemIndex WHERE {conditions} "
            "ORDER BY System.DateModified DESC"
        )

        connection = win32com.client.Dispatch("ADODB.Connection")
        connection.Open(
            "Provider=Search.CollatorDSO;Extended Properties='Application=Windows';"
        )

        recordset = win32com.client.Dispatch("ADODB.Recordset")
        recordset.Open(sql, connection)

        paths = []

        while not recordset.EOF:

            paths.append(recordset.Fields.Item("System.ItemPathDisplay").Value)
            recordset.MoveNext()

        recordset.Close()
        connection.Close()

        return paths

    finally:

        pythoncom.CoUninitialize()


class FileSearch:

    def __init__(self, guard, index_query=None, home=None):

        self.guard = guard
        self.index_query = index_query or windows_index_query
        self.home = Path(home) if home else Path.home()

    # ------------------------------------------------

    def search(self, query, limit=15):
        """
        Returns [{"path", "name", "type"}] best match first.
        """

        terms = [t for t in query.lower().split() if t]

        if not terms:
            return []

        try:
            paths = self.index_query(terms, INDEX_FETCH)

        except Exception as e:

            log.info("Windows Search unavailable (%s); walking folders", e)
            paths = []

        if not paths:
            paths = self._walk(terms)

        results = []
        seen = set()

        for raw in paths:

            path = self.guard.for_read(raw)

            if path is None or self.guard.is_junk(path) or str(path) in seen:
                continue

            seen.add(str(path))

            results.append({
                "path": str(path),
                "name": path.name,
                "type": "folder" if path.is_dir() else "file",
            })

        results.sort(key=lambda r: self._rank(r["name"], terms))

        return results[:limit]

    @staticmethod
    def _rank(name, terms):

        name = name.lower()
        joined = " ".join(terms)

        if name == joined or os.path.splitext(name)[0] == joined:
            return 0

        if name.startswith(joined):
            return 1

        return 2

    def _walk(self, terms):
        """
        Fallback: scan the user's folders for a few seconds.
        """

        deadline = time.time() + WALK_SECONDS
        found = []

        # everyday folders first
        roots = [self.home / n for n in ("Desktop", "Documents", "Downloads")]
        roots.append(self.home)

        for root in roots:

            for folder, dirs, files in os.walk(root):

                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in {"appdata", "node_modules", ".git", "site-packages", "__pycache__"}
                ]

                for name in dirs + files:

                    lowered = name.lower()

                    if all(t in lowered for t in terms):
                        found.append(os.path.join(folder, name))

                if time.time() > deadline or len(found) >= 60:
                    return found

        return found
