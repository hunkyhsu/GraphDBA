"""
Tests for mcp_servers/security_utils.py

Manual Testing
--------------
Prerequisites: virtual environment activated, no database needed.
Run:  pytest tests/security_utils_test.py -v
Expected: all tests PASSED, zero failures.
"""

import pytest

from mcp_servers.security_utils import (
    DLPValidator,
    QueryLimiter,
    SQLInjectionDetector,
    SecurityViolationError,
)


# -- SQLInjectionDetector -------------------------------------------------


class TestSQLInjectionDetector:
    """Validate that the detector blocks dangerous SQL while allowing safe reads."""

    def test_allows_safe_select(self) -> None:
        SQLInjectionDetector.validate_query("SELECT * FROM users WHERE id = 1")

    def test_allows_safe_select_with_join(self) -> None:
        SQLInjectionDetector.validate_query(
            "SELECT a.id, b.name FROM users a JOIN orders b ON a.id = b.user_id"
        )

    def test_allows_safe_select_with_subquery(self) -> None:
        SQLInjectionDetector.validate_query(
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)"
        )

    @pytest.mark.parametrize(
        "query",
        [
            "DROP TABLE users",
            "DELETE FROM orders",
            "UPDATE users SET role = 'admin'",
            "INSERT INTO logs VALUES (1)",
            "TRUNCATE events",
            "ALTER TABLE users ADD COLUMN x INT",
            "GRANT ALL ON users TO attacker",
            "REVOKE SELECT ON users FROM readonly",
            "CREATE TABLE evil (id INT)",
            "RENAME TABLE users TO pwned",
        ],
    )
    def test_blocks_dangerous_keyword(self, query: str) -> None:
        with pytest.raises(SecurityViolationError):
            SQLInjectionDetector.validate_query(query)

    @pytest.mark.parametrize(
        "query",
        [
            "SELECT 1; DROP TABLE users",
            "SELECT * FROM users WHERE name = '' OR 1=1",
            "SELECT * FROM users UNION SELECT * FROM secrets",
        ],
    )
    def test_blocks_injection_pattern(self, query: str) -> None:
        with pytest.raises(SecurityViolationError):
            SQLInjectionDetector.validate_query(query)

    def test_rejects_empty_query(self) -> None:
        with pytest.raises(SecurityViolationError):
            SQLInjectionDetector.validate_query("")

    def test_rejects_whitespace_only_query(self) -> None:
        with pytest.raises(SecurityViolationError):
            SQLInjectionDetector.validate_query("   ")

    def test_allows_dml_when_flag_is_set(self) -> None:
        SQLInjectionDetector.validate_query(
            "DELETE FROM logs WHERE ts < now()", allow_dml=True
        )


# -- QueryLimiter ----------------------------------------------------------


class TestQueryLimiter:
    """Verify automatic LIMIT injection and capping."""

    def test_adds_default_limit(self) -> None:
        assert QueryLimiter.inject_limit("SELECT * FROM orders") == (
            "SELECT * FROM orders LIMIT 100"
        )

    def test_adds_custom_limit(self) -> None:
        assert QueryLimiter.inject_limit("SELECT * FROM orders", max_rows=50) == (
            "SELECT * FROM orders LIMIT 50"
        )

    def test_reduces_limit_when_too_high(self) -> None:
        assert QueryLimiter.inject_limit("SELECT * FROM orders LIMIT 500") == (
            "SELECT * FROM orders LIMIT 100"
        )

    def test_keeps_safe_existing_limit(self) -> None:
        assert QueryLimiter.inject_limit("SELECT * FROM orders LIMIT 10") == (
            "SELECT * FROM orders LIMIT 10"
        )

    def test_leaves_non_select_unchanged(self) -> None:
        assert QueryLimiter.inject_limit("SHOW TABLES") == "SHOW TABLES"

    def test_strips_trailing_semicolon(self) -> None:
        result = QueryLimiter.inject_limit("SELECT 1;")
        assert result == "SELECT 1 LIMIT 100"


# -- DLPValidator ----------------------------------------------------------


class TestDLPValidator:
    """Verify sensitive-data detection in query text / results."""

    def test_detects_credit_card(self) -> None:
        assert "credit_card" in DLPValidator.scan_for_sensitive_data(
            "Card: 4111-1111-1111-1111"
        )

    def test_detects_ssn(self) -> None:
        assert "ssn" in DLPValidator.scan_for_sensitive_data("SSN: 123-45-6789")

    def test_returns_empty_for_clean_text(self) -> None:
        assert DLPValidator.scan_for_sensitive_data("Hello world") == []

    def test_detects_multiple_types(self) -> None:
        text = "SSN 123-45-6789 card 4111-1111-1111-1111"
        detected = DLPValidator.scan_for_sensitive_data(text)
        assert "credit_card" in detected
        assert "ssn" in detected
