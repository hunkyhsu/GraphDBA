"""
Tests for utils/logger.py

Manual Testing
--------------
Prerequisites: virtual environment activated, no database needed.
Run:  pytest tests/logger_test.py -v
Expected: all tests PASSED, zero failures.
"""

import json
import logging

import pytest

from utils.logger import (
    JSONFormatter,
    TextFormatter,
    get_trace_id,
    new_trace_id,
    set_trace_id,
    setup_logging,
)


# -- Trace ID management ---------------------------------------------------


class TestTraceID:
    """Verify trace-ID generation, propagation, and override."""

    def test_new_trace_id_returns_hex_string(self) -> None:
        tid = new_trace_id()
        assert len(tid) == 16
        int(tid, 16)  # must be valid hex

    def test_get_trace_id_returns_current(self) -> None:
        tid = new_trace_id()
        assert get_trace_id() == tid

    def test_set_trace_id_overrides(self) -> None:
        set_trace_id("custom-id-12345")
        assert get_trace_id() == "custom-id-12345"

    def test_successive_new_trace_ids_differ(self) -> None:
        t1 = new_trace_id()
        t2 = new_trace_id()
        assert t1 != t2


# -- JSONFormatter ---------------------------------------------------------


class TestJSONFormatter:
    """Verify structured JSON log output."""

    def _make_record(self, name: str, msg: str) -> logging.LogRecord:
        return logging.LogRecord(
            name=name, level=logging.INFO, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )

    def test_output_is_valid_json(self) -> None:
        new_trace_id()
        fmt = JSONFormatter()
        record = self._make_record("test", "hello")
        parsed = json.loads(fmt.format(record))
        assert parsed["message"] == "hello"
        assert parsed["level"] == "INFO"

    def test_includes_trace_id(self) -> None:
        tid = new_trace_id()
        fmt = JSONFormatter()
        record = self._make_record("test", "msg")
        parsed = json.loads(fmt.format(record))
        assert parsed["trace_id"] == tid

    @pytest.mark.parametrize(
        "logger_name, expected_component",
        [
            ("mcp_servers.read_probe", "mcp"),
            ("agents.supervisor", "agent"),
            ("rag.pgvector_store", "rag"),
            ("api.main", "api"),
        ],
    )
    def test_component_tag(self, logger_name: str, expected_component: str) -> None:
        new_trace_id()
        fmt = JSONFormatter()
        record = self._make_record(logger_name, "msg")
        parsed = json.loads(fmt.format(record))
        assert parsed["component"] == expected_component

    def test_no_component_for_unknown_logger(self) -> None:
        new_trace_id()
        fmt = JSONFormatter()
        record = self._make_record("some.other", "msg")
        parsed = json.loads(fmt.format(record))
        assert "component" not in parsed

    def test_extra_fields_attached(self) -> None:
        new_trace_id()
        fmt = JSONFormatter()
        record = self._make_record("mcp_servers.read", "query executed")
        record.tool_name = "execute_safe_select"  # type: ignore[attr-defined]
        record.duration_ms = 42  # type: ignore[attr-defined]
        parsed = json.loads(fmt.format(record))
        assert parsed["tool_name"] == "execute_safe_select"
        assert parsed["duration_ms"] == 42


# -- TextFormatter ---------------------------------------------------------


class TestTextFormatter:
    """Verify human-readable log format."""

    def test_contains_level_and_message(self) -> None:
        new_trace_id()
        fmt = TextFormatter()
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="", lineno=0,
            msg="oops", args=(), exc_info=None,
        )
        line = fmt.format(record)
        assert "WARNING" in line
        assert "oops" in line


# -- setup_logging ---------------------------------------------------------


class TestSetupLogging:
    """Verify top-level logging bootstrap."""

    def test_json_mode(self) -> None:
        setup_logging(level="DEBUG", fmt="json")
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert isinstance(root.handlers[0].formatter, JSONFormatter)

    def test_text_mode(self) -> None:
        setup_logging(level="INFO", fmt="text")
        root = logging.getLogger()
        assert isinstance(root.handlers[0].formatter, TextFormatter)

    def test_suppresses_noisy_loggers(self) -> None:
        setup_logging()
        assert logging.getLogger("httpx").level >= logging.WARNING
        assert logging.getLogger("urllib3").level >= logging.WARNING
