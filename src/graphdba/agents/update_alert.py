from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from graphdba.utils.external_call import single_external_call
if TYPE_CHECKING:
    from mcp.client.session import ClientSession

logger = logging.getLogger(__name__)

MCP_TIMEOUT_S = 10.0

async def update_alert(
    mcp_client: ClientSession,
    alert_id: str,
    status: str,
    failure_reason: str | None = None,
    escalation_reason: str | None = None,
    solved_at: str | None = None,
    resolved_at: str | None = None,
    clear_failure_reason: bool = False,
) -> str | None:
    """Return failure reason when persistence fails; otherwise return None."""
    result, fail_reason = await single_external_call(
        coro=mcp_client.call_tool(
            name="update_alert_status",
            arguments={"input_data":{
                "alert_id": alert_id,
                "status": status,
                "failure_reason": failure_reason,
                "escalation_reason": escalation_reason,
                "solved_at": solved_at,
                "resolved_at": resolved_at,
                "clear_failure_reason": clear_failure_reason,
            }},
        ),
        timeout=MCP_TIMEOUT_S,
        label="Update Alert",
        logger=logger,
    )
    if fail_reason:
        return fail_reason
    if result.isError:
        return result.content[0].text if result.content else "Unknown MCP tool error"
    return None
