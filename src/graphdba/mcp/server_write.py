from __future__ import annotations
import inspect
import logging
from functools import wraps
from mcp.server.fastmcp import FastMCP, Context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from graphdba.mcp.models import (
    AlertResponse, CreateAlertInput, UpdateAlertStatusInput,
    ProposeActionInput, UpdateTicketInput
)
from graphdba.mcp.tools_write import (
    AlertConflictError, AlertNotFoundError, DBOperationError,
    _insert_alert, _update_alert,
    _approve_ticket,
    _execute_ticket,
    _propose_ticket,
)
from graphdba.database.connection_pool import write_lifespan

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
@mcp_write.tool()
@inject_pool
async def insert_alert(input_data: CreateAlertInput, context: Context, pool = None) -> str:
    """Insert an alert record and return the alert id."""
    try:
        result = await _insert_alert(input_data, pool)
        return str(result.alert_id)
    except AlertConflictError as e:
        logger.warning("Alert depulication")
        raise ValueError(f"MCP Tool Error: {str(e)}")
    except DBOperationError:
        logger.exception("Unexcepected error in inserting alert")
        raise RuntimeError("MCP System Failure: DB is unavailable")

@mcp_write.tool()
@inject_pool
async def update_alert_status(input_data: UpdateAlertStatusInput, context: Context, pool = None) -> dict:
    """Update an alert workflow status and return the updated alert."""
    try:
        result = await _update_alert(input_data, pool)
        return {"status": "success", "alert": result.model_dump(mode="json")}
    except AlertNotFoundError as e:
        logger.warning("Failed to update alert status")
        raise ValueError(f"MCP Tool Error: {str(e)}")
    except DBOperationError:
        logger.exception("Unexcepected error in updating alert")
        raise RuntimeError("MCP System Failure: DB is unavailable")

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
async def execute_ticket(ticket_id: str, context: Context, pool = None) -> str:
    """Executes a previously approved ticket within a safe, rollback-capable transaction. Returns execution status."""
    result, error = await _execute_ticket(ticket_id, pool)
    if error:
        raise ValueError(error)
    return result

if __name__ == "__main__":
    mcp_write.run()
