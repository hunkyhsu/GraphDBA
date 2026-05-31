from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from graphdba.utils.external_call import single_external_call
if TYPE_CHECKING:
    from mcp.client.session import ClientSession

logger = logging.getLogger(__name__)

MCP_TIMEOUT_S = 10.0

async def get_alert_status(mcp_client: ClientSession,alert_id: str) -> tuple[str | None, str | None]:
    """Return failure reason when persistence fails; otherwise return None."""
    result, fail_reason = await single_external_call(
        coro=mcp_client.call_tool(
            name="get_alert_by_id",
            arguments={"alert_id":alert_id},
        ),
        timeout=MCP_TIMEOUT_S,
        label="Get Alert Status",
        logger=logger,
    )
    if fail_reason:
        return None, fail_reason
    if result.isError:
        return None, result.content[0].text if result.content else "Unknown MCP tool error"
    alert_data = json.loads(result.content[0].text)
    return alert_data["status"], None