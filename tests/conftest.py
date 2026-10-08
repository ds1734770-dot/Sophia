import pytest

from app.brain import gemini_client


@pytest.fixture(autouse=True)
def isolated_model_pool(tmp_path, monkeypatch):
    """
    Cooldowns are shared per process and usage is written to disk;
    give every test a clean pool and a throwaway usage file.
    """

    monkeypatch.setattr(gemini_client, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.setattr(gemini_client.GeminiClient, "_pool", None)
