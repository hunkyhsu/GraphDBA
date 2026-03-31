"""
Integration tests for mcp_servers/read_probe_server.py

These tests run against a real Docker PostgreSQL instance (agent_test_db).
They verify that ReadProbeServer correctly reads schema, enforces read-only
transactions, rejects dangerous SQL, and respects row limits / timeouts.

Manual Testing
--------------
Prerequisites:
  - PostgreSQL running and reachable via: psql -d agent_test_db
  - Virtual environment activated with project dependencies installed
  - Environment variables set (or .env.dev loaded):
      POSTGRES_HOST=localhost
      POSTGRES_PORT=5432
      POSTGRES_DB=agent_test_db
      POSTGRES_USER=hunkyhsu
      POSTGRES_PASSWORD=

Run:
  pytest tests/read_probe_server_test.py -v

Expected results:
  All tests PASSED. The fixture creates and tears down test tables automatically.

Negative tests:
  - execute_safe_select with DROP/DELETE/UPDATE → SecurityViolationError
  - explain_query with DML → SecurityViolationError
  - Rows returned are capped at max_result_rows

Cleanup:
  The session-scoped fixture drops all test tables on teardown.
"""

import os
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor

# Point settings at the test database before importing application code.
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "agent_test_db")
os.environ.setdefault("POSTGRES_USER", "hunkyhsu")
os.environ.setdefault("POSTGRES_PASSWORD", "")

from config.settings import DatabaseSettings
from mcp_servers.read_probe_server import ReadProbeServer
from mcp_servers.security_utils import SecurityViolationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_conn():
    """Return a psycopg2 connection using the same settings the server uses."""
    s = DatabaseSettings()
    return psycopg2.connect(**s.connection_params)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_tables():
    """Create test tables once per session and drop them on teardown."""
    conn = _admin_conn()
    conn.autocommit = True
    cur = conn.cursor()

    # -- schema
    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) NOT NULL,
            email VARCHAR(100),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES test_users(id),
            amount NUMERIC(10, 2) NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_orders_user_id
        ON test_orders(user_id)
    """)

    # -- seed data
    cur.execute("DELETE FROM test_orders")
    cur.execute("DELETE FROM test_users")

    cur.execute("""
        INSERT INTO test_users (username, email) VALUES
            ('alice', 'alice@example.com'),
            ('bob',   'bob@example.com'),
            ('carol', 'carol@example.com')
    """)

    # Insert enough rows to test row-limiting (150 orders > default 100 limit)
    cur.execute("""
        INSERT INTO test_orders (user_id, amount, status)
        SELECT
            (u.id),
            ROUND((RANDOM() * 1000)::numeric, 2),
            CASE WHEN RANDOM() > 0.5 THEN 'completed' ELSE 'pending' END
        FROM test_users u,
             generate_series(1, 50) AS g
    """)

    cur.close()
    conn.close()

    yield  # tests run here

    # -- teardown
    conn = _admin_conn()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS test_orders CASCADE")
    cur.execute("DROP TABLE IF EXISTS test_users CASCADE")
    cur.close()
    conn.close()


@pytest.fixture()
def server(test_tables):
    """Provide a ReadProbeServer instance that is closed after the test."""
    srv = ReadProbeServer()
    yield srv
    srv.close()


# ---------------------------------------------------------------------------
# get_db_schema
# ---------------------------------------------------------------------------

class TestGetDbSchema:
    """Verify schema retrieval for real tables."""

    def test_returns_columns(self, server: ReadProbeServer) -> None:
        result = server.get_db_schema(["test_users"])
        schema = result["schemas"]["test_users"]
        # Rows are tuples: (column_name, data_type, char_max_len, is_nullable, default)
        col_names = [c[0] for c in schema["columns"]]
        assert "id" in col_names
        assert "username" in col_names
        assert "email" in col_names

    def test_returns_indexes(self, server: ReadProbeServer) -> None:
        result = server.get_db_schema(["test_orders"])
        schema = result["schemas"]["test_orders"]
        # Rows are tuples: (indexname, indexdef)
        idx_names = [i[0] for i in schema["indexes"]]
        assert any("idx_test_orders_user_id" in n for n in idx_names)

    def test_returns_foreign_keys(self, server: ReadProbeServer) -> None:
        result = server.get_db_schema(["test_orders"])
        schema = result["schemas"]["test_orders"]
        # Rows are tuples: (constraint_name, column_name, foreign_table, foreign_column)
        fk_cols = [fk[1] for fk in schema["foreign_keys"]]
        assert "user_id" in fk_cols

    def test_nonexistent_table_returns_empty(self, server: ReadProbeServer) -> None:
        result = server.get_db_schema(["no_such_table_xyz"])
        schema = result["schemas"]["no_such_table_xyz"]
        assert schema["columns"] == []
        assert schema["indexes"] == []
        assert schema["foreign_keys"] == []

    def test_multiple_tables(self, server: ReadProbeServer) -> None:
        result = server.get_db_schema(["test_users", "test_orders"])
        assert "test_users" in result["schemas"]
        assert "test_orders" in result["schemas"]


# ---------------------------------------------------------------------------
# execute_safe_select
# ---------------------------------------------------------------------------

class TestExecuteSafeSelect:
    """Verify read-only SELECT with safety guardrails."""

    def test_basic_select(self, server: ReadProbeServer) -> None:
        result = server.execute_safe_select("SELECT * FROM test_users")
        assert result["row_count"] == 3

    def test_select_with_where(self, server: ReadProbeServer) -> None:
        result = server.execute_safe_select(
            "SELECT username FROM test_users WHERE username = 'alice'"
        )
        assert result["row_count"] == 1
        # Result rows are tuples; first column is username
        assert result["results"][0][0] == "alice"

    def test_select_with_join(self, server: ReadProbeServer) -> None:
        result = server.execute_safe_select("""
            SELECT u.username, o.amount
            FROM test_users u
            JOIN test_orders o ON o.user_id = u.id
        """)
        assert result["row_count"] > 0

    def test_row_limit_enforced(self, server: ReadProbeServer) -> None:
        """150 orders exist but default limit is 100 — verify capping."""
        result = server.execute_safe_select("SELECT * FROM test_orders")
        assert result["row_count"] <= 100
        assert result["limited"] is True

    def test_rejects_drop(self, server: ReadProbeServer) -> None:
        with pytest.raises(SecurityViolationError):
            server.execute_safe_select("DROP TABLE test_users")

    def test_rejects_delete(self, server: ReadProbeServer) -> None:
        with pytest.raises(SecurityViolationError):
            server.execute_safe_select("DELETE FROM test_users")

    def test_rejects_update(self, server: ReadProbeServer) -> None:
        with pytest.raises(SecurityViolationError):
            server.execute_safe_select("UPDATE test_users SET username = 'evil'")

    def test_rejects_insert(self, server: ReadProbeServer) -> None:
        with pytest.raises(SecurityViolationError):
            server.execute_safe_select("INSERT INTO test_users (username) VALUES ('x')")

    def test_rejects_truncate(self, server: ReadProbeServer) -> None:
        with pytest.raises(SecurityViolationError):
            server.execute_safe_select("TRUNCATE test_users")

    def test_rejects_sql_injection(self, server: ReadProbeServer) -> None:
        with pytest.raises(SecurityViolationError):
            server.execute_safe_select(
                "SELECT * FROM test_users WHERE username = '' OR 1=1"
            )

    def test_rejects_union_injection(self, server: ReadProbeServer) -> None:
        with pytest.raises(SecurityViolationError):
            server.execute_safe_select(
                "SELECT username FROM test_users UNION SELECT table_name FROM information_schema.tables"
            )


# ---------------------------------------------------------------------------
# explain_query
# ---------------------------------------------------------------------------

class TestExplainQuery:
    """Verify EXPLAIN returns execution plans within read-only context."""

    def test_explain_basic(self, server: ReadProbeServer) -> None:
        result = server.explain_query("SELECT * FROM test_users")
        assert "execution_plan" in result
        assert result["analyzed"] is False
        assert len(result["execution_plan"]) > 0

    def test_explain_analyze(self, server: ReadProbeServer) -> None:
        result = server.explain_query("SELECT * FROM test_users", analyze=True)
        assert result["analyzed"] is True
        # EXPLAIN ANALYZE output contains timing info
        plan_text = str(result["execution_plan"])
        assert "actual" in plan_text.lower() or "time" in plan_text.lower()

    def test_explain_with_join(self, server: ReadProbeServer) -> None:
        result = server.explain_query("""
            SELECT u.username, o.amount
            FROM test_users u
            JOIN test_orders o ON o.user_id = u.id
            WHERE o.status = 'completed'
        """)
        assert len(result["execution_plan"]) > 0

    def test_explain_rejects_dml(self, server: ReadProbeServer) -> None:
        with pytest.raises(SecurityViolationError):
            server.explain_query("DELETE FROM test_users WHERE id = 1")

    def test_explain_rejects_ddl(self, server: ReadProbeServer) -> None:
        with pytest.raises(SecurityViolationError):
            server.explain_query("DROP TABLE test_users")


# ---------------------------------------------------------------------------
# get_blocking_locks
# ---------------------------------------------------------------------------

class TestGetBlockingLocks:
    """Verify blocking-lock query runs without errors."""

    def test_returns_lock_info(self, server: ReadProbeServer) -> None:
        result = server.get_blocking_locks()
        assert "blocking_locks" in result
        assert "count" in result
        # Normally no blocking locks in test env
        assert isinstance(result["blocking_locks"], list)


# ---------------------------------------------------------------------------
# get_pg_stat_statements (may not be available)
# ---------------------------------------------------------------------------

class TestGetPgStatStatements:
    """Test pg_stat_statements retrieval — skip if extension not installed."""

    def test_returns_or_raises(self, server: ReadProbeServer) -> None:
        """If pg_stat_statements is installed, returns results; otherwise raises."""
        conn = _admin_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'"
        )
        has_ext = cur.fetchone() is not None
        cur.close()
        conn.close()

        if has_ext:
            result = server.get_pg_stat_statements(limit=5, min_duration_ms=0)
            assert "slow_queries" in result
            assert "count" in result
        else:
            with pytest.raises(Exception):
                server.get_pg_stat_statements(limit=5, min_duration_ms=0)


# ---------------------------------------------------------------------------
# Connection pool behaviour
# ---------------------------------------------------------------------------

class TestConnectionPool:
    """Verify connection pool cap is respected."""

    def test_pool_does_not_exceed_max(self, server: ReadProbeServer) -> None:
        # Issue enough calls to potentially create many connections
        for _ in range(10):
            server.get_db_schema(["test_users"])
        assert len(server.connection_pool) <= server.max_connections

    def test_close_clears_pool(self, test_tables) -> None:
        srv = ReadProbeServer()
        srv.get_db_schema(["test_users"])
        assert len(srv.connection_pool) > 0
        srv.close()
        assert len(srv.connection_pool) == 0


# ---------------------------------------------------------------------------
# Read-only transaction enforcement
# ---------------------------------------------------------------------------

class TestReadOnlyEnforcement:
    """Verify the database rejects writes even if security_utils is bypassed."""

    def test_readonly_transaction_blocks_insert(self, server: ReadProbeServer) -> None:
        """Directly attempt an INSERT inside a read-only transaction."""
        conn = server._get_connection()
        from mcp_servers.security_utils import with_readonly_transaction

        with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
            with with_readonly_transaction(conn) as cur:
                cur.execute(
                    "INSERT INTO test_users (username) VALUES ('should_fail')"
                )

    def test_readonly_transaction_blocks_delete(self, server: ReadProbeServer) -> None:
        conn = server._get_connection()
        from mcp_servers.security_utils import with_readonly_transaction

        with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
            with with_readonly_transaction(conn) as cur:
                cur.execute("DELETE FROM test_users WHERE id = 1")

    def test_data_unchanged_after_failed_write(self, server: ReadProbeServer) -> None:
        """Confirm rows are intact after a rejected write attempt."""
        result = server.execute_safe_select(
            "SELECT COUNT(*) AS cnt FROM test_users"
        )
        count_before = result["results"][0][0]

        conn = server._get_connection()
        from mcp_servers.security_utils import with_readonly_transaction

        with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
            with with_readonly_transaction(conn) as cur:
                cur.execute(
                    "INSERT INTO test_users (username) VALUES ('phantom')"
                )

        result = server.execute_safe_select(
            "SELECT COUNT(*) AS cnt FROM test_users"
        )
        count_after = result["results"][0][0]
        assert count_before == count_after
