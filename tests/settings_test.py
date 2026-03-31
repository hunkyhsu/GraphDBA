"""
Tests for config/settings.py

Manual Testing
--------------
Prerequisites: virtual environment activated, no database needed.
Run:  pytest tests/settings_test.py -v
Expected: all tests PASSED, zero failures.
"""

import os

import pytest
from pydantic import ValidationError

from config.settings import (
    DatabaseSettings,
    LLMSettings,
    QuerySafetySettings,
    Settings,
    WriteDatabaseSettings,
)


# -- DatabaseSettings ------------------------------------------------------


class TestDatabaseSettings:
    """Verify database config loads from env and builds connection strings."""

    def test_loads_defaults(self) -> None:
        s = DatabaseSettings()
        assert s.host == "localhost"
        assert s.port == 5432

    def test_reads_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_HOST", "db.prod")
        monkeypatch.setenv("POSTGRES_PORT", "5433")
        monkeypatch.setenv("POSTGRES_DB", "mydb")
        monkeypatch.setenv("POSTGRES_USER", "admin")
        monkeypatch.setenv("POSTGRES_PASSWORD", "s3cret")

        s = DatabaseSettings()
        assert s.host == "db.prod"
        assert s.port == 5433
        assert s.db == "mydb"

    def test_connection_string_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_HOST", "h")
        monkeypatch.setenv("POSTGRES_PORT", "1234")
        monkeypatch.setenv("POSTGRES_DB", "d")
        monkeypatch.setenv("POSTGRES_USER", "u")
        monkeypatch.setenv("POSTGRES_PASSWORD", "p")

        s = DatabaseSettings()
        assert s.connection_string == "postgresql://u:p@h:1234/d"

    def test_connection_params_dict(self) -> None:
        s = DatabaseSettings()
        params = s.connection_params
        assert set(params.keys()) == {"host", "port", "database", "user", "password"}

    def test_rejects_invalid_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_PORT", "99999")
        with pytest.raises(ValidationError):
            DatabaseSettings()


# -- WriteDatabaseSettings -------------------------------------------------


class TestWriteDatabaseSettings:
    """Verify write-database config uses its own env prefix."""

    def test_uses_write_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_WRITE_HOST", "write-host")
        monkeypatch.setenv("POSTGRES_WRITE_USER", "dba")
        monkeypatch.setenv("POSTGRES_WRITE_PASSWORD", "wpass")

        s = WriteDatabaseSettings()
        assert s.host == "write-host"
        assert s.user == "dba"

    def test_write_and_read_are_independent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("POSTGRES_HOST", "read-host")
        monkeypatch.setenv("POSTGRES_WRITE_HOST", "write-host")

        r = DatabaseSettings()
        w = WriteDatabaseSettings()
        assert r.host != w.host


# -- LLMSettings -----------------------------------------------------------


class TestLLMSettings:
    """Verify multi-provider LLM configuration."""

    def test_defaults(self) -> None:
        s = LLMSettings()
        assert s.primary_llm_provider == "openai"
        assert s.deepseek_base_url == "https://api.deepseek.com"
        assert s.deepseek_model == "deepseek-chat"

    def test_rejects_short_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "short")
        with pytest.raises(ValidationError):
            LLMSettings()

    def test_accepts_valid_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "a" * 40)
        s = LLMSettings()
        assert s.openai_api_key is not None

    def test_deepseek_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "d" * 40)
        monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-coder")

        s = LLMSettings()
        assert s.deepseek_api_key is not None
        assert s.deepseek_model == "deepseek-coder"


# -- QuerySafetySettings --------------------------------------------------


class TestQuerySafetySettings:
    """Verify safety-limit boundaries."""

    def test_defaults(self) -> None:
        s = QuerySafetySettings()
        assert s.max_query_timeout_seconds == 30
        assert s.max_result_rows == 100

    def test_rejects_timeout_below_minimum(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MAX_QUERY_TIMEOUT_SECONDS", "1")
        with pytest.raises(ValidationError):
            QuerySafetySettings()


# -- Settings (top-level) -------------------------------------------------


class TestSettings:
    """Verify the aggregated Settings object and its validation helper."""

    def test_validate_warns_on_missing_passwords(self) -> None:
        s = Settings()
        warnings = s.validate_configuration()
        assert any("database password" in w.lower() for w in warnings)

    def test_validate_warns_on_default_jwt_secret(self) -> None:
        s = Settings()
        warnings = s.validate_configuration()
        assert any("JWT" in w for w in warnings)

    def test_validate_warns_when_no_llm_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

        s = Settings()
        warnings = s.validate_configuration()
        assert any("No LLM API keys" in w for w in warnings)

    def test_no_llm_warning_when_key_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "x" * 40)
        s = Settings()
        warnings = s.validate_configuration()
        assert not any("No LLM API keys" in w for w in warnings)
