from chronos.config.settings import get_env_var


def test_get_env_var_preserves_hash(monkeypatch):
    """Values containing '#' must be preserved; python-dotenv owns comment handling."""
    monkeypatch.setenv("CHRONOS_TEST_HASH", "p@ss#word")
    assert get_env_var("CHRONOS_TEST_HASH") == "p@ss#word"


def test_get_env_var_strips_quotes_and_whitespace(monkeypatch):
    monkeypatch.setenv("CHRONOS_TEST_QUOTES", '  "hello"  ')
    assert get_env_var("CHRONOS_TEST_QUOTES") == "hello"


def test_get_env_var_default(monkeypatch):
    monkeypatch.delenv("CHRONOS_TEST_MISSING", raising=False)
    assert get_env_var("CHRONOS_TEST_MISSING", "fallback") == "fallback"
    assert get_env_var("CHRONOS_TEST_MISSING") is None
