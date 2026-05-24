from __future__ import annotations
import inspect
import logging
from functools import wraps
from typing import Any
from mcp.server.fastmcp import FastMCP, Context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

from graphdba.mcp.tools_write import _execute_ticket, _propose_ticket, _approve_ticket
from graphdba.database.connection_pool import write_lifespan
from graphdba.mcp.models import ProposeActionInput, ExecuteActionInput, UpdateTicketInput

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

mcp_write = FastMCP("Write MCP Server", lifespan=write_lifespan)
# Table alerts MCP

# Table hypotheses MCP

# Table change_tickets MCP
@mcp_write.tool()
@inject_pool
async def propose_ticket(input_data: ProposeActionInput, context: Context, pool = None) -> str:
    """Stages a tuning action for DBA approval. Does NOT execute the SQL. Returns ticket id."""
    ticket_id, error = await _propose_ticket(input_data, pool)
    if error:
        raise ValueError(error)
    return ticket_id

@mcp_write.tool()
@inject_pool
async def approve_ticket(input_data: UpdateTicketInput, context: Context, pool = None) -> str:
    """Update the ticket as approval. Returns ticket id."""
    ticket_id, error = await _approve_ticket(input_data, pool)
    if error:
        raise ValueError(error)
    return ticket_id

@mcp_write.tool()
@inject_pool
async def execute_ticket(input_data: ExecuteActionInput, context: Context, pool = None) -> str:
    """Executes a previously approved ticket within a safe, rollback-capable transaction. Returns execution status."""
    result, error = await _execute_ticket(input_data, pool)
    if error:
        raise ValueError(error)
    return result

if __name__ == "__main__":
    mcp_write.run()