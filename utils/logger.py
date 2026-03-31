"""
Structured logging infrastructure for GraphDBA.

Provides JSON-formatted logging with trace IDs for request correlation.
"""

import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Optional

# Context variable for trace ID propagation across async calls
_trace_id: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)


def get_trace_id() -> str:
    """Get current trace ID, or generate a new one."""
    tid = _trace_id.get()
    if tid is None:
        tid = uuid.uuid4().hex[:16]
        _trace_id.set(tid)
    return tid


def set_trace_id(trace_id: str) -> None:
    """Set trace ID for the current context."""
    _trace_id.set(trace_id)


def new_trace_id() -> str:
    """Generate and set a new trace ID."""
    tid = uuid.uuid4().hex[:16]
    _trace_id.set(tid)
    return tid


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": get_trace_id(),
        }

        if record.name.startswith("mcp_servers"):
            log_entry["component"] = "mcp"
        elif record.name.startswith("agents"):
            log_entry["component"] = "agent"
        elif record.name.startswith("rag"):
            log_entry["component"] = "rag"
        elif record.name.startswith("api"):
            log_entry["component"] = "api"

        if hasattr(record, 'tool_name'):
            log_entry["tool_name"] = record.tool_name
        if hasattr(record, 'query'):
            log_entry["query"] = record.query[:200]
        if hasattr(record, 'duration_ms'):
            log_entry["duration_ms"] = record.duration_ms

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now().strftime("%H:%M:%S")
        tid = get_trace_id()
        return f"[{ts}] {record.levelname:<8} [{tid}] {record.name}: {record.getMessage()}"


def setup_logging(level: str = "INFO", fmt: str = "json") -> None:
    """
    Configure application-wide logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        fmt: Output format ('json' or 'text')
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(TextFormatter())

    root.addHandler(handler)

    # Suppress noisy third-party loggers
    for name in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)
