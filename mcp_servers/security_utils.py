"""
Security utilities for MCP servers.

Provides SQL injection prevention, transaction wrappers, query timeout enforcement,
row limiting, and data loss prevention (DLP) validation.
"""

import re
import logging
from typing import Optional, Callable, Any
from contextlib import contextmanager
from functools import wraps

logger = logging.getLogger(__name__)


class SecurityViolationError(Exception):
    """Raised when a security policy is violated."""
    pass


class SQLInjectionDetector:
    """Detects potential SQL injection attempts."""

    # Dangerous SQL keywords that should be blocked in read-only contexts
    DANGEROUS_KEYWORDS = [
        r'\bDROP\b', r'\bDELETE\b', r'\bTRUNCATE\b', r'\bINSERT\b',
        r'\bUPDATE\b', r'\bALTER\b', r'\bCREATE\b', r'\bGRANT\b',
        r'\bREVOKE\b', r'\bEXECUTE\b', r'\bCALL\b', r'\bMERGE\b',
        r'\bREPLACE\b', r'\bRENAME\b', r'\bCOMMIT\b', r'\bROLLBACK\b',
        r'\bSAVEPOINT\b', r'\bLOCK\b', r'\bUNLOCK\b'
    ]

    # Suspicious patterns
    SUSPICIOUS_PATTERNS = [
        r';\s*DROP',  # Statement chaining
        r'--',  # SQL comments
        r'/\*.*\*/',  # Multi-line comments
        r'\bOR\b\s+[\'"]?\d+[\'"]?\s*=\s*[\'"]?\d+[\'"]?',  # OR 1=1
        r'\bUNION\b.*\bSELECT\b',  # UNION injection
        r'\bINTO\b\s+OUTFILE\b',  # File operations
        r'\bLOAD_FILE\b',  # File reading
        r'xp_cmdshell',  # SQL Server command execution
    ]

    @classmethod
    def validate_query(cls, query: str, allow_dml: bool = False) -> None:
        """
        Validate SQL query for security violations.

        Args:
            query: SQL query to validate
            allow_dml: If False, blocks DML operations

        Raises:
            SecurityViolationError: If query contains dangerous patterns
        """
        if not query or not query.strip():
            raise SecurityViolationError("Empty query not allowed")

        query_upper = query.upper()

        # Check for dangerous keywords
        if not allow_dml:
            for keyword_pattern in cls.DANGEROUS_KEYWORDS:
                if re.search(keyword_pattern, query_upper, re.IGNORECASE):
                    raise SecurityViolationError(
                        f"Dangerous SQL keyword detected: {keyword_pattern}"
                    )

        # Check for suspicious patterns
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                raise SecurityViolationError(
                    f"Suspicious SQL pattern detected: {pattern}"
                )

        logger.info(f"Query validated successfully: {query[:100]}...")


class QueryLimiter:
    """Enforces query result limits and timeouts."""

    DEFAULT_MAX_ROWS = 100
    DEFAULT_TIMEOUT_SECONDS = 30

    @classmethod
    def inject_limit(cls, query: str, max_rows: int = DEFAULT_MAX_ROWS) -> str:
        """
        Inject LIMIT clause into SELECT query if not present.

        Args:
            query: SQL query
            max_rows: Maximum rows to return

        Returns:
            Query with LIMIT clause
        """
        query = query.strip().rstrip(';')
        query_upper = query.upper()

        # Only inject LIMIT for SELECT queries
        if not query_upper.startswith('SELECT'):
            return query

        # Check if LIMIT already exists
        if re.search(r'\bLIMIT\b', query_upper):
            # Verify existing limit doesn't exceed max
            limit_match = re.search(r'\bLIMIT\s+(\d+)', query_upper)
            if limit_match:
                existing_limit = int(limit_match.group(1))
                if existing_limit > max_rows:
                    logger.warning(
                        f"Reducing LIMIT from {existing_limit} to {max_rows}"
                    )
                    query = re.sub(
                        r'\bLIMIT\s+\d+',
                        f'LIMIT {max_rows}',
                        query,
                        flags=re.IGNORECASE
                    )
            return query

        # Inject LIMIT clause
        return f"{query} LIMIT {max_rows}"


class DLPValidator:
    """Data Loss Prevention validator for sensitive data patterns."""

    # Patterns for sensitive data
    SENSITIVE_PATTERNS = {
        'credit_card': r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
        'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'api_key': r'\b(sk-[a-zA-Z0-9]{32,}|[a-zA-Z0-9]{32,})\b',
    }

    @classmethod
    def scan_for_sensitive_data(cls, text: str) -> list[str]:
        """
        Scan text for sensitive data patterns.

        Args:
            text: Text to scan

        Returns:
            List of detected sensitive data types
        """
        detected = []
        for data_type, pattern in cls.SENSITIVE_PATTERNS.items():
            if re.search(pattern, text):
                detected.append(data_type)
                logger.warning(f"Detected {data_type} in query/result")

        return detected


@contextmanager
def with_readonly_transaction(connection):
    """
    Context manager for read-only transactions.

    Ensures transaction is read-only and automatically rolls back.

    Args:
        connection: Database connection object

    Yields:
        Database cursor

    Example:
        with with_readonly_transaction(conn) as cursor:
            cursor.execute("SELECT * FROM users")
            results = cursor.fetchall()
    """
    cursor = None
    try:
        cursor = connection.cursor()

        # Force read-only mode
        cursor.execute("SET TRANSACTION READ ONLY")
        logger.debug("Transaction set to READ ONLY mode")

        yield cursor

    except Exception as e:
        logger.error(f"Error in read-only transaction: {e}")
        if connection:
            connection.rollback()
        raise
    finally:
        # Always rollback to ensure no changes
        if connection:
            connection.rollback()
            logger.debug("Transaction rolled back")
        if cursor:
            cursor.close()


def enforce_query_timeout(timeout_seconds: int = QueryLimiter.DEFAULT_TIMEOUT_SECONDS):
    """
    Decorator to enforce query timeout.

    Args:
        timeout_seconds: Maximum execution time

    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Set statement timeout for PostgreSQL
            connection = kwargs.get('connection') or (args[0] if args else None)
            if connection:
                cursor = connection.cursor()
                cursor.execute(f"SET statement_timeout = {timeout_seconds * 1000}")
                cursor.close()
                logger.debug(f"Query timeout set to {timeout_seconds}s")

            return func(*args, **kwargs)
        return wrapper
    return decorator


def validate_readonly_query(func: Callable) -> Callable:
    """
    Decorator to validate queries are read-only.

    Checks query for dangerous keywords before execution.
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        query = kwargs.get('query') or (args[0] if args else None)
        if query:
            SQLInjectionDetector.validate_query(query, allow_dml=False)
        return func(*args, **kwargs)
    return wrapper


def inject_row_limit(max_rows: int = QueryLimiter.DEFAULT_MAX_ROWS):
    """
    Decorator to inject row limit into SELECT queries.

    Args:
        max_rows: Maximum rows to return
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            query = kwargs.get('query')
            if query:
                kwargs['query'] = QueryLimiter.inject_limit(query, max_rows)
            elif args:
                args = list(args)
                args[0] = QueryLimiter.inject_limit(args[0], max_rows)
                args = tuple(args)
            return func(*args, **kwargs)
        return wrapper
    return decorator
