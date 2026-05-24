from __future__ import annotations
import inspect
import logging
from typing import Any
from functools import wraps
from mcp.server.fastmcp import FastMCP

from mcp.server.fastmcp import Context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
from graphdba.mcp.models import ExplainQueryInput, SafeSelectInput, SlowQueryFilter
from graphdba.database.connection_pool import read_lifespan
from graphdba.mcp.tools_read import _explain_query, _execute_safe_select, _get_blocking_locks, _get_pg_stat_statements

mcp_read = FastMCP("Read MCP Server", lifespan=read_lifespan)

def inject_pool(func):
    _sig = inspect.signature(func)

    @wraps(func)
    async def wrapper(*args, **kwargs):
        bound = _sig.bind(*args, **kwargs)
        bound.apply_defaults()
        context: Context = bound.arguments.get("context")
        if context and "db_pool" in context.request_context.lifespan_context:
            kwargs["pool"] = context.request_context.lifespan_context["db_pool"]
        return await func(*args, **kwargs)
    return wrapper

@mcp_read.tool()
@inject_pool
async def explain_query(input_data: ExplainQueryInput, context: Context, pool = None) -> dict[str, Any]:
    """Generates the PostgreSQL EXPLAIN execution plan for a given SELECT query."""
    return await _explain_query(input_data, pool)

@mcp_read.tool()
@inject_pool
async def execute_safe_select(input_data: SafeSelectInput, context: Context, pool = None) -> dict[str, Any]:
    """Execute read-only SELECT query with safety limits."""
    return await _execute_safe_select(input_data, pool)

@mcp_read.tool()
@inject_pool
async def get_pg_stat_statements(filters: SlowQueryFilter, context: Context, pool = None) -> dict[str, Any]:
    """Get slow query statistics from pg_stat_statements. Used to diagnose performance anomalies."""
    return await _get_pg_stat_statements(filters, pool)

@mcp_read.tool()
@inject_pool
async def get_blocking_locks(context: Context, pool = None) -> dict[str, Any]:
    """Get current blocking locks and waiting sessions. Used to diagnose locking pile-ups."""
    return await _get_blocking_locks(pool)

if __name__ == "__main__":
    mcp_read.run()
