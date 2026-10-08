import pytest

from app.adapters.gemini_adapter import GeminiAdapter
from app.brain import gemini_client as module
from app.brain.model_pool import ModelPool, UsageTracker, classify
from app.memory.memory_filter import MemoryFilter


def test_split_system_messages():

    system, turns = GeminiAdapter.split_system([
        {"role": "system", "content": "be Sophia"},
        {"role": "system", "content": "profile: x"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ])

    assert system == "be Sophia\n\nprofile: x"
    assert [t["role"] for t in turns] == ["user", "assistant"]


def test_convert_skips_system_and_maps_roles():

    contents = GeminiAdapter.convert([
        {"role": "system", "content": "ignored"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ])

    assert [c.role for c in contents] == ["user", "model"]


# ---------------------------------------------------------------
# Error classification and cooldowns
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "error, kind",
    [
        ("429 RESOURCE_EXHAUSTED. Please retry in 12.5s.", "quota"),
        ("429 RESOURCE_EXHAUSTED GenerateRequestsPerDay", "quota"),
        ("503 UNAVAILABLE", "server"),
        ("504 DEADLINE_EXCEEDED", "server"),
        ("500 INTERNAL", "server"),
        ("404 NOT_FOUND model gone", "gone"),
        ("400 INVALID_ARGUMENT", None),
        ("401 API key not valid", None),
    ],
)
def test_classify(error, kind):

    assert classify(error)[0] == kind


def test_quota_cooldown_uses_the_retry_delay():

    assert classify("429 RESOURCE_EXHAUSTED retry in 12.5s")[1] == pytest.approx(13.5)
    assert classify("429 RESOURCE_EXHAUSTED GenerateRequestsPerDay")[1] >= 3600


def test_pool_skips_cooling_models_until_they_recover():

    now = [0.0]
    pool = ModelPool(["a", "b"], clock=lambda: now[0])

    assert pool.available() == ["a", "b"]

    pool.mark_failed("a", "429 RESOURCE_EXHAUSTED retry in 30s")

    assert pool.available() == ["b"]
    assert pool.soonest_wait(["a"]) == pytest.approx(31)

    now[0] = 40

    assert pool.available() == ["a", "b"]


def test_bad_request_is_not_a_model_failure():

    pool = ModelPool(["a"])

    assert pool.mark_failed("a", "400 INVALID_ARGUMENT") is None
    assert pool.available() == ["a"]


def test_usage_tracker(tmp_path):

    tracker = UsageTracker(tmp_path / "u.json")

    tracker.record("m1", "ok")
    tracker.record("m1", "ok")
    tracker.record("m1", "quota")

    assert tracker.today() == {"m1": {"ok": 2, "quota": 1}}
    assert "m1" in tracker.report()


def test_usage_tracker_never_raises(tmp_path):

    # a directory where a file is expected
    tracker = UsageTracker(tmp_path)

    tracker.record("m", "ok")

    assert tracker.today() == {}


# ---------------------------------------------------------------
# GeminiClient with a model chain
# ---------------------------------------------------------------

class FakeModels:
    """
    script: {model: [outcome, ...]}; an outcome is an Exception to
    raise or any other value to return.
    """

    def __init__(self, script):
        self.script = {m: list(o) for m, o in script.items()}
        self.calls = []
        self.config = None

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        self.config = config
        outcome = self.script[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_client(monkeypatch, script, primary="main", fallbacks=("backup", "lite"), light="lite"):

    models = FakeModels(script)

    class FakeGenaiClient:
        def __init__(self, **kwargs):
            self.models = models

    monkeypatch.setattr(module.genai, "Client", FakeGenaiClient)
    monkeypatch.setattr(module.time, "sleep", lambda s: None)

    client = module.GeminiClient()
    client.chain = [primary, *fallbacks]
    client.settings.light_model = light

    return client, models


CONVERSATION = [
    {"role": "system", "content": "be Sophia"},
    {"role": "user", "content": "hi"},
]

QUOTA = RuntimeError("429 RESOURCE_EXHAUSTED retry in 300s")


def test_system_text_goes_to_system_instruction(monkeypatch):

    client, models = make_client(monkeypatch, {"main": ["ok"]})

    assert client.generate(CONVERSATION, "") == "ok"
    assert models.config.system_instruction == "be Sophia"


def test_falls_back_when_the_primary_is_out_of_quota(monkeypatch):

    client, models = make_client(monkeypatch, {"main": [QUOTA], "backup": ["from backup"]})

    assert client.generate(CONVERSATION, "") == "from backup"
    assert models.calls == ["main", "backup"]


def test_dead_model_is_skipped_on_the_next_request(monkeypatch):

    client, models = make_client(
        monkeypatch, {"main": [QUOTA], "backup": ["one", "two"]}
    )

    client.generate(CONVERSATION, "")
    client.generate(CONVERSATION, "")

    # main was only tried once; the second request went straight to backup
    assert models.calls == ["main", "backup", "backup"]


def test_server_errors_also_fall_back(monkeypatch):

    client, models = make_client(
        monkeypatch,
        {"main": [RuntimeError("504 DEADLINE_EXCEEDED")], "backup": ["ok"]},
    )

    assert client.generate(CONVERSATION, "") == "ok"


def test_all_models_exhausted_raises_the_quota_error(monkeypatch):

    client, models = make_client(
        monkeypatch,
        {"main": [QUOTA], "backup": [QUOTA], "lite": [QUOTA]},
    )

    with pytest.raises(RuntimeError, match="429"):
        client.generate(CONVERSATION, "")

    # and the next request fails fast without calling anything
    calls = len(models.calls)

    with pytest.raises(RuntimeError, match="429"):
        client.generate(CONVERSATION, "")

    assert len(models.calls) == calls


def test_bad_request_is_raised_without_trying_other_models(monkeypatch):

    client, models = make_client(
        monkeypatch, {"main": [RuntimeError("400 INVALID_ARGUMENT")]}
    )

    with pytest.raises(RuntimeError, match="400"):
        client.generate(CONVERSATION, "")

    assert models.calls == ["main"]


def test_background_work_prefers_the_light_model(monkeypatch):

    client, models = make_client(monkeypatch, {"lite": ["facts"]})

    assert client.generate(CONVERSATION, "", light=True) == "facts"
    assert models.calls == ["lite"]


# ---------------------------------------------------------------
# Memory extraction is only worth a request for personal statements
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "my name is Alex",
        "I'm studying at State University",
        "I love playing chess",
        "my favorite language is Java",
        "call me Al",
        "Actually my favourite food is biryani",
        "remember that I use Windows",
    ],
)
def test_personal_statements_are_extracted(text):

    assert MemoryFilter.should_extract(text)


@pytest.mark.parametrize(
    "text",
    [
        "hello",
        "what is a binary tree",
        "explain recursion with an example",
        "how do I reverse a linked list?",
        "ok thanks",
        "write a python function to sort a list",
    ],
)
def test_other_messages_are_not(text):

    assert not MemoryFilter.should_extract(text)
