
from app.context import system_profile as sp
from app.memory.summarizer import Summarizer


class Mem:
    def __init__(self, items):
        self.items = list(items)
    def get_history(self):
        return list(self.items)
    def load(self, items):
        self.items = list(items)


class Sum:
    text = ""
    def get(self):
        return self.text
    def set(self, t):
        self.text = t


def test_messages_added_during_a_summary_are_kept():

    memory = Mem([{"n": i} for i in range(40)])
    summary = Sum()

    def slow(previous, old):
        memory.items.append({"n": "new"})      # arrives while summarising
        return "summary"

    assert Summarizer(slow, trigger=30, keep=10).maybe_summarize(memory, summary)

    assert summary.get() == "summary"
    assert memory.items[-1] == {"n": "new"}
    assert len(memory.items) == 11


def test_a_summary_is_dropped_if_history_changed_underneath():

    memory = Mem([{"n": i} for i in range(40)])

    def rewrite(previous, old):
        memory.items = [{"n": "other"}]
        return "summary"

    assert not Summarizer(rewrite, trigger=30, keep=10).maybe_summarize(memory, Sum())


def test_system_profile_describes_the_pc(monkeypatch, tmp_path):

    (tmp_path / "Downloads").mkdir()
    monkeypatch.setattr(sp, "_static", {"text": None, "built": 0.0})
    monkeypatch.setattr(sp, "open_windows", lambda: ["Notes - Notepad"])

    text = sp.system_profile(
        lambda: [{"name": "Spotify"}, {"name": "Notepad"}], home=tmp_path
    )

    assert "Downloads" in text and "Spotify" in text
    assert "Open right now: Notes - Notepad" in text


def test_system_profile_survives_a_broken_app_index(monkeypatch, tmp_path):

    monkeypatch.setattr(sp, "_static", {"text": None, "built": 0.0})
    monkeypatch.setattr(sp, "open_windows", lambda: [])

    def broken():
        raise OSError("no index")

    assert sp.system_profile(broken, home=tmp_path) == ""
