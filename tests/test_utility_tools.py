import zipfile

import pytest

from app.brain.tool_context import ToolContext
from app.file.path_guard import PathGuard
from app.tools.registry import Risk, ToolRegistry
from app.tools.utility_tools import convert_units_value, register_utility_tools


def make(tmp_path, fetch=None, processes=None, recent=None):

    guard = PathGuard(home=tmp_path)
    registry = ToolRegistry()

    register_utility_tools(
        registry, guard,
        fetch=fetch or (lambda *a, **k: {}),
        process_source=processes,
        recent_folder=recent,
    )

    return registry


def run(registry, tool, **args):

    # confirmed=True: the tier itself is checked in separate tests
    return registry.execute(tool, args, ToolContext(), confirmed=True)


@pytest.mark.parametrize("value,src,dst,expected", [
    (5, "miles", "km", 8.04672),
    (100, "c", "f", 212),
    (32, "F", "C", 0),
    (1, "kg", "lb", 2.2046),
    (2, "GB", "MB", 2048),
    (60, "mph", "km/h", 96.56),
])
def test_unit_conversions(value, src, dst, expected):

    ok, result = convert_units_value(value, src, dst)

    assert ok and result == pytest.approx(expected, rel=1e-3)


def test_unknown_or_mixed_units_are_refused():

    assert not convert_units_value(1, "kg", "km")[0]
    assert not convert_units_value(1, "parsec", "km")[0]


def test_convert_units_tool_reads_naturally(tmp_path):

    result = run(make(tmp_path), "convert_units", value=5, from_unit="miles", to_unit="km")

    assert result.ok and "8.047" in result.message


def test_currency_uses_the_rate_service(tmp_path):

    seen = {}

    def fetch(url, params=None, as_json=True):
        seen.update(params)
        return {"date": "2026-10-08", "rates": {"INR": 8350.0}}

    result = run(make(tmp_path, fetch), "convert_currency",
                 amount=100, from_currency="usd", to_currency="inr")

    assert result.ok and "8,350" in result.message
    assert seen["from"] == "USD" and seen["to"] == "INR"


def test_currency_rejects_bad_codes_and_survives_outages(tmp_path):

    assert not run(make(tmp_path), "convert_currency",
                   amount=1, from_currency="dollars", to_currency="inr").ok

    def down(*a, **k):
        raise OSError("offline")

    assert not run(make(tmp_path, down), "convert_currency",
                   amount=1, from_currency="usd", to_currency="inr").ok


def test_define_word(tmp_path):

    data = {"en": [{"partOfSpeech": "Noun",
                    "definitions": [{"definition": 'a <a href="x">thing</a>'}]}]}

    result = run(make(tmp_path, lambda *a, **k: data), "define_word", word="thing")

    assert result.ok and "a thing" in result.message

    assert not run(make(tmp_path), "define_word", word="../etc").ok


def test_wikipedia_summary(tmp_path):

    def fetch(url, params=None, as_json=True):
        if "api.php" in url:
            return {"query": {"search": [{"title": "Alan Turing"}]}}
        return {"title": "Alan Turing", "extract": "English mathematician."}

    result = run(make(tmp_path, fetch), "wikipedia_summary", topic="turing")

    assert result.ok and "mathematician" in result.message
    assert "treat as data" in result.message


def test_news_headlines(tmp_path):

    xml = ("<rss><channel><item><title>Big thing</title><pubDate>Thu, 08 Oct 2026 10:00</pubDate></item>"
           "<item><title>Other</title><pubDate>Thu, 08 Oct 2026 09:00</pubDate></item></channel></rss>")

    result = run(make(tmp_path, lambda *a, **k: xml), "news_headlines", count=1)

    assert result.ok and "Big thing" in result.message and "Other" not in result.message


def test_list_processes_groups_and_filters(tmp_path):

    procs = lambda: [
        {"pid": 1, "name": "chrome.exe", "memory": 300 * 1024 ** 2},
        {"pid": 2, "name": "chrome.exe", "memory": 200 * 1024 ** 2},
        {"pid": 3, "name": "code.exe", "memory": 100 * 1024 ** 2},
    ]

    registry = make(tmp_path, processes=procs)

    everything = run(registry, "list_processes")
    assert everything.message.splitlines()[0].startswith("chrome.exe: 500.0 MB (2 processes)")

    only = run(registry, "list_processes", name="code")
    assert "chrome" not in only.message


def test_ending_programs_always_asks_with_a_warning_and_spares_windows(tmp_path):

    registry = make(tmp_path)

    assert registry.tools["end_process"].risk is Risk.DANGEROUS
    assert not registry.tools["end_process"].trustable

    for name in ("explorer.exe", "csrss", "svchost.exe"):
        refused = run(registry, "end_process", name=name)
        assert not refused.ok and "Windows" in refused.message


def test_folder_sizes_ranks_biggest_first(tmp_path):

    (tmp_path / "big").mkdir()
    (tmp_path / "big" / "a.bin").write_bytes(b"x" * 5000)
    (tmp_path / "small.txt").write_text("hi")

    result = run(make(tmp_path), "folder_sizes", path=str(tmp_path))

    lines = result.message.splitlines()

    assert result.ok and "big/" in lines[1] and "small.txt" in lines[2]


def test_recent_files_lists_newest_first(tmp_path):

    recent = tmp_path / "Recent"
    recent.mkdir()

    for i, name in enumerate(["old.lnk", "new.lnk"]):
        f = recent / name
        f.write_text("")
        import os
        os.utime(f, (1000 + i * 100, 1000 + i * 100))

    result = run(make(tmp_path, recent=recent), "recent_files")

    assert result.message.splitlines()[1] == "- new"


def test_zip_and_unzip_round_trip(tmp_path):

    folder = tmp_path / "Docs" / "project"
    folder.mkdir(parents=True)
    (folder / "a.txt").write_text("hello")
    (folder / "id_rsa").write_text("PRIVATE")

    registry = make(tmp_path)

    made = run(registry, "zip_item", path=str(folder))

    assert made.ok

    archive = folder.parent / "project.zip"

    with zipfile.ZipFile(archive) as z:
        names = z.namelist()

    assert any(n.endswith("a.txt") for n in names)
    assert not any("id_rsa" in n for n in names)

    # a second time it will not overwrite
    assert not run(registry, "zip_item", path=str(folder)).ok

    archive.rename(folder.parent / "copy.zip")

    assert run(registry, "unzip_item", path=str(folder.parent / "copy.zip")).ok
    assert (folder.parent / "copy" / "project" / "a.txt").read_text() == "hello"


def test_unzip_blocks_path_traversal_and_programs(tmp_path):

    docs = tmp_path / "Docs"
    docs.mkdir()
    bad = docs / "evil.zip"

    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../escaped.txt", "x")
        z.writestr("run.exe", "MZ")
        z.writestr("ok.txt", "fine")

    assert run(make(tmp_path), "unzip_item", path=str(bad)).ok

    assert not (docs / "escaped.txt").exists()
    assert not (docs / "evil" / "run.exe").exists()
    assert (docs / "evil" / "ok.txt").exists()


def test_changing_tools_need_confirmation(tmp_path):

    registry = make(tmp_path)

    for name in ("zip_item", "unzip_item", "set_windows_theme"):
        assert registry.tools[name].risk is Risk.CONFIRM


def test_password_has_the_requested_length_and_mix(tmp_path):

    message = run(make(tmp_path), "generate_password", length=20).message

    password = message.splitlines()[0]

    assert len(password) == 20
    assert any(c.isdigit() for c in password) and any(c.isupper() for c in password)


def test_lookups_can_run_in_parallel():

    from app.tools.registry import PARALLEL_SAFE

    for name in ("convert_units", "wikipedia_summary", "news_headlines", "folder_sizes"):
        assert name in PARALLEL_SAFE
