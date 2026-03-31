"""
Read Probe MCP Server - Read-only database access for AI agents.

Provides safe, read-only tools for querying database metrics, schema,
and performance statistics. All queries are wrapped in READ-ONLY transactions
with automatic rollback.
"""

import json
import logging
from typing import Any, Optional
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from config.settings import get_settings
from mcp_servers.security_utils import (
    SQLInjectionDetector,
    QueryLimiter,
    SecurityViolationError,
    with_readonly_transaction
)

logger = logging.getLogger(__name__)
settings = get_settings()


class ReadProbeServer:
    """Read-only MCP server for database diagnostics."""

    def __init__(self):
        self.server = Server("read-probe-server")
        self.connection_pool = []
        self.max_connections = 5
        self._setup_tools()

    def _get_connection(self):
        """Get database connection from pool or create new one."""
        if len(self.connection_pool) < self.max_connections:
            conn = psycopg2.connect(**settings.database.connection_params)
            self.connection_pool.append(conn)
            logger.info(f"Created new connection (pool size: {len(self.connection_pool)})")
            return conn
        return self.connection_pool[0]

    def _setup_tools(self):
        """Register MCP tools."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="get_db_schema",
                    description="Get database schema (DDL) for specified tables",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "table_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of table names to retrieve schema for"
                            }
                        },
                        "required": ["table_names"]
                    }
                ),
                Tool(
                    name="get_pg_stat_statements",
                    description="Get slow query statistics from pg_stat_statements",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Number of queries to return",
                                "default": 10
                            },
                            "min_duration_ms": {
                                "type": "integer",
                                "description": "Minimum query duration in milliseconds",
                                "default": 100
                            }
                        }
                    }
                ),
                Tool(
                    name="get_blocking_locks",
                    description="Get current blocking locks and waiting sessions",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="explain_query",
                    description="Get execution plan for a query (automatically rolled back)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "SQL query to explain"
                            },
                            "analyze": {
                                "type": "boolean",
                                "description": "Run EXPLAIN ANALYZE (executes query)",
                                "default": False
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="execute_safe_select",
                    description="Execute read-only SELECT query with safety limits",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "SELECT query to execute"
                            }
                        },
                        "required": ["query"]
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            """Handle tool calls."""
            try:
                if name == "get_db_schema":
                    result = self.get_db_schema(arguments["table_names"])
                elif name == "get_pg_stat_statements":
                    result = self.get_pg_stat_statements(
                        arguments.get("limit", 10),
                        arguments.get("min_duration_ms", 100)
                    )
                elif name == "get_blocking_locks":
                    result = self.get_blocking_locks()
                elif name == "explain_query":
                    result = self.explain_query(
                        arguments["query"],
                        arguments.get("analyze", False)
                    )
                elif name == "execute_safe_select":
                    result = self.execute_safe_select(arguments["query"])
                else:
                    raise ValueError(f"Unknown tool: {name}")

                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str)
                )]

            except SecurityViolationError as e:
                logger.error(f"Security violation in {name}: {e}")
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": f"Security violation: {str(e)}"})
                )]
            except Exception as e:
                logger.error(f"Error in {name}: {e}", exc_info=True)
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)})
                )]

    def get_db_schema(self, table_names: list[str]) -> dict:
        """
        Get DDL for specified tables.

        Args:
            table_names: List of table names

        Returns:
            Dictionary with table schemas
        """
        conn = self._get_connection()
        schemas = {}

        with with_readonly_transaction(conn) as cursor:
            for table_name in table_names:
                # Get table definition
                cursor.execute("""
                    SELECT
                        column_name,
                        data_type,
                        character_maximum_length,
                        is_nullable,
                        column_default
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))

                columns = cursor.fetchall()

                # Get indexes
                cursor.execute("""
                    SELECT
                        indexname,
                        indexdef
                    FROM pg_indexes
                    WHERE tablename = %s
                """, (table_name,))

                indexes = cursor.fetchall()

                # Get foreign keys
                cursor.execute("""
                    SELECT
                        tc.constraint_name,
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND tc.table_name = %s
                """, (table_name,))

                foreign_keys = cursor.fetchall()

                schemas[table_name] = {
                    "columns": columns,
                    "indexes": indexes,
                    "foreign_keys": foreign_keys
                }

        logger.info(f"Retrieved schema for {len(table_names)} tables")
        return {"schemas": schemas}

    def get_pg_stat_statements(self, limit: int = 10, min_duration_ms: int = 100) -> dict:
        """
        Get slow query statistics.

        Args:
            limit: Number of queries to return
            min_duration_ms: Minimum query duration

        Returns:
            Dictionary with slow queries
        """
        conn = self._get_connection()

        with with_readonly_transaction(conn) as cursor:
            cursor.execute(f"""
                SELECT
                    query,
                    calls,
                    total_exec_time,
                    mean_exec_time,
                    max_exec_time,
                    rows
                FROM pg_stat_statements
                WHERE mean_exec_time > %s
                ORDER BY mean_exec_time DESC
                LIMIT %s
            """, (min_duration_ms, limit))

            queries = cursor.fetchall()

        logger.info(f"Retrieved {len(queries)} slow queries")
        return {"slow_queries": queries, "count": len(queries)}

    def get_blocking_locks(self) -> dict:
        """
        Get current blocking locks.

        Returns:
            Dictionary with blocking locks information
        """
        conn = self._get_connection()

        with with_readonly_transaction(conn) as cursor:
            cursor.execute("""
                SELECT
                    blocked_locks.pid AS blocked_pid,
                    blocked_activity.usename AS blocked_user,
                    blocking_locks.pid AS blocking_pid,
                    blocking_activity.usename AS blocking_user,
                    blocked_activity.query AS blocked_statement,
                    blocking_activity.query AS blocking_statement,
                    blocked_activity.wait_event_type,
                    blocked_activity.wait_event
                FROM pg_catalog.pg_locks blocked_locks
                JOIN pg_catalog.pg_stat_activity blocked_activity
                    ON blocked_activity.pid = blocked_locks.pid
                JOIN pg_catalog.pg_locks blocking_locks
                    ON blocking_locks.locktype = blocked_locks.locktype
                    AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
                    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
                    AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
                    AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
                    AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
                    AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
                    AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
                    AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
                    AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
                    AND blocking_locks.pid != blocked_locks.pid
                JOIN pg_catalog.pg_stat_activity blocking_activity
                    ON blocking_activity.pid = blocking_locks.pid
                WHERE NOT blocked_locks.granted
            """)

            locks = cursor.fetchall()

        logger.info(f"Retrieved {len(locks)} blocking locks")
        return {"blocking_locks": locks, "count": len(locks)}

    def explain_query(self, query: str, analyze: bool = False) -> dict:
        """
        Get execution plan for query.

        Args:
            query: SQL query
            analyze: Whether to run EXPLAIN ANALYZE

        Returns:
            Dictionary with execution plan
        """
        # Validate query
        SQLInjectionDetector.validate_query(query, allow_dml=False)

        conn = self._get_connection()

        with with_readonly_transaction(conn) as cursor:
            explain_cmd = "EXPLAIN ANALYZE" if analyze else "EXPLAIN"
            cursor.execute(f"{explain_cmd} {query}")
            plan = cursor.fetchall()

        logger.info(f"Generated execution plan for query")
        return {"execution_plan": plan, "analyzed": analyze}

    def execute_safe_select(self, query: str) -> dict:
        """
        Execute read-only SELECT query with safety limits.

        Args:
            query: SELECT query

        Returns:
            Dictionary with query results
        """
        # Validate query
        SQLInjectionDetector.validate_query(query, allow_dml=False)

        # Inject row limit
        limited_query = QueryLimiter.inject_limit(
            query,
            settings.query_safety.max_result_rows
        )

        conn = self._get_connection()

        with with_readonly_transaction(conn) as cursor:
            # Set statement timeout
            cursor.execute(
                f"SET statement_timeout = {settings.query_safety.max_query_timeout_seconds * 1000}"
            )

            # Execute query
            cursor.execute(limited_query)
            results = cursor.fetchall()

        logger.info(f"Executed safe SELECT, returned {len(results)} rows")
        return {
            "results": results,
            "row_count": len(results),
            "limited": len(results) >= settings.query_safety.max_result_rows
        }

    def close(self):
        """Close all database connections."""
        for conn in self.connection_pool:
            conn.close()
        self.connection_pool.clear()
        logger.info("Closed all database connections")


async def main():
    """Run the MCP server."""
    read_server = ReadProbeServer()

    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("Read Probe MCP Server started")
            await read_server.server.run(
                read_stream,
                write_stream,
                read_server.server.create_initialization_options()
            )
    finally:
        read_server.close()


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
