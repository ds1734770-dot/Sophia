import pytest

from app.adapters.gemini_adapter import GeminiAdapter
from app.brain import gemini_client as module


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


class FakeModels:

    def __init__(self, failures):
        self.failures = list(failures)
        self.calls = 0
        self.config = None

    def generate_content(self, model, contents, config):
        self.calls += 1
        self.config = config
        if self.failures:
            raise RuntimeError(self.failures.pop(0))
        return "ok"


def make_client(monkeypatch, failures):

    models = FakeModels(failures)

    class FakeGenaiClient:
        def __init__(self, **kwargs):
            self.models = models

    monkeypatch.setattr(module.genai, "Client", FakeGenaiClient)
    monkeypatch.setattr(module.time, "sleep", lambda s: None)

    return module.GeminiClient(), models


CONVERSATION = [
    {"role": "system", "content": "be Sophia"},
    {"role": "user", "content": "hi"},
]


def test_system_text_goes_to_system_instruction(monkeypatch):

    client, models = make_client(monkeypatch, [])

    assert client.generate(CONVERSATION, "") == "ok"
    assert models.config.system_instruction == "be Sophia"


def test_retries_temporary_errors(monkeypatch):

    client, models = make_client(monkeypatch, ["503 UNAVAILABLE", "503 UNAVAILABLE"])

    assert client.generate(CONVERSATION, "") == "ok"
    assert models.calls == 3


def test_gives_up_after_max_attempts(monkeypatch):

    client, models = make_client(monkeypatch, ["503 UNAVAILABLE"] * 5)

    with pytest.raises(RuntimeError):
        client.generate(CONVERSATION, "")

    assert models.calls == client.MAX_ATTEMPTS


def test_does_not_retry_other_errors(monkeypatch):

    client, models = make_client(monkeypatch, ["400 INVALID"])

    with pytest.raises(RuntimeError):
        client.generate(CONVERSATION, "")

    assert models.calls == 1
