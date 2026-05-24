from __future__ import annotations
from typing import Any, TYPE_CHECKING
import logging
from graphdba.mcp.guard_read import ReadSecurityError, validate_query, limit_rows
from graphdba.config.settings import get_settings
from graphdba.utils.external_call import db_readonly_fetch

if TYPE_CHECKING:
    import asyncpg
    from graphdba.mcp.models import ExplainQueryInput, SlowQueryFilter, SafeSelectInput

logger = logging.getLogger(__name__)

async def _explain_query(input_data: ExplainQueryInput, pool: asyncpg.Pool) -> dict[str, Any]:
    try:
        validate_query(input_data.query)
    except ReadSecurityError as e:
        return {"error": str(e)}

    explain_cmd = "EXPLAIN ANALYZE" if input_data.run_analyze else "EXPLAIN"
    full_query = f"{explain_cmd} {input_data.query}"
    records, error = await db_readonly_fetch(pool, lambda conn: conn.fetch(full_query), "_explain_query", logger)
    
    if error:
        return {"error": error}
    return {"execution_plan": [dict(r) for r in records], "analyzed": input_data.run_analyze}

async def _execute_safe_select(input_data: SafeSelectInput, pool) -> dict[str, Any]:
    try:
        validate_query(input_data.query)
    except ReadSecurityError as e:
        return {"error": str(e)}

    limit_query = limit_rows(input_data.query, get_settings().security.max_result_rows)
    records, error = await db_readonly_fetch(pool, lambda conn: conn.fetch(limit_query), "_execute_safe_select", logger)
    
    if error:
        return {"error": error}
    return {"results": [dict(r) for r in records]}

async def _get_pg_stat_statements(filters: SlowQueryFilter, pool) -> dict[str, Any]:
    records, error = await db_readonly_fetch(
        pool,
        lambda conn: conn.fetch("""
            SELECT query, calls, total_exec_time, mean_exec_time, rows
            FROM pg_stat_statements
            WHERE mean_exec_time > $1
            ORDER BY mean_exec_time DESC
            LIMIT $2
        """, filters.min_duration_ms, filters.limit),
        "_get_pg_stat_statements",
        logger
    )

    if error:
        return {"error": error}
    return {"slow_queries": [dict(r) for r in records]}

async def _get_blocking_locks(pool) -> dict[str, Any]:
    records, error = await db_readonly_fetch(
        pool,
        lambda conn: conn.fetch("""
            SELECT
                blocked_locks.pid AS blocked_pid,
                blocked_activity.usename AS blocked_user,
                blocking_locks.pid AS blocking_pid,
                blocking_activity.usename AS blocking_user,
                blocked_activity.query AS blocked_statement,
                blocking_activity.query AS blocking_statement
            FROM pg_catalog.pg_locks blocked_locks
            JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
            JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
                AND blocking_locks.pid != blocked_locks.pid
            JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
            WHERE NOT blocked_locks.granted;
        """),
        "_get_blocking_locks",
        logger
    )
    
    if error:
        return {"error": error}
    return {"blocking_locks": [dict(r) for r in records]}
