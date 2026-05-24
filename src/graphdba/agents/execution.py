from __future__ import annotations
import logging
import asyncio
from typing import TYPE_CHECKING
from graphdba.agents.state import ApprovalDecision, WorkflowStatus
from graphdba.utils.external_call import single_external_call

if TYPE_CHECKING:
    from mcp.client.session import ClientSession
    from graphdba.agents.state import AgentState, AgentStateUpdate, FinalPlan

logger = logging.getLogger(__name__)

class ExecutionNode:
    MCP_TIMEOUT_S = 30.0
    def __init__(self, mcp_client: ClientSession):
        self.mcp_client = mcp_client
    
    async def __call__(self, state: AgentState) -> AgentStateUpdate:
        decision = state["approval_decision"]
        logger.info("Human approval is %s", decision)
        if decision == ApprovalDecision.REJECTED:
            reason = state.get("human_feedback", "No feedback reason provided.")
            logger.warning("Ticket rejected by human DBA for reason: %s", reason)
            return {
                "workflow_status": WorkflowStatus.COMPLETED.value,
                "failed_reason": f"Human rejected: {reason}"
            }
        # APPROVED
        logger.info("Executing ticket through MCP...")
        result, fail_reason = await single_external_call(
            coro=self.mcp_client.call_tool(
                name="execute_ticket",
                arguments={
                    "input_data": {
                        "ticket_id": state["ticket_id"],
                    }
                }
            ),
            timeout=self.MCP_TIMEOUT_S,
            label="Executing Ticket",
            logger=logger
        )
        if fail_reason:
            return {
                "workflow_status": WorkflowStatus.FAILED.value,
                "failed_reason": fail_reason,
            }
        if result.isError:
            error_text = result.content[0].text if result.content else "Unknown MCP tool error"
            return {
                "workflow_status": WorkflowStatus.FAILED.value,
                "failed_reason": f"propose_ticket MCP tool error: {error_text}",
            }
        logger.info("Successfully execute a ticket to TABLE change_tickets")
        return {
            "workflow_status": WorkflowStatus.COMPLETED.value,
        }