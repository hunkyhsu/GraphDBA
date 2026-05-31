from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from graphdba.agents.state import WorkflowStatus
from graphdba.utils.external_call import single_external_call
from graphdba.agents.state import AgentState, AgentStateUpdate, FinalPlan

if TYPE_CHECKING:
    from mcp.client.session import ClientSession

logger = logging.getLogger(__name__)

class ProposingNode:
    MCP_TIMEOUT_S = 10.0
    """Propose the ticket about the final plan to TABLE change_tickets."""

    def __init__(self, mcp_client: ClientSession):
        self.mcp_client = mcp_client

    async def __call__(self, state: AgentState) -> AgentStateUpdate:
        plan: FinalPlan = FinalPlan.model_validate(state["final_plan"])
        logger.info("Proposing ticket through MCP...")
        result, fail_reason = await single_external_call(
            coro=self.mcp_client.call_tool(
                name="propose_ticket",
                arguments={
                    "input_data": {
                        "alert_fingerprint": plan.target_alert_id,
                        "alert_payload": {k: v for k, v in state["alert"].items() if k != "raw_payload"},
                        "hypotheses": state["current_hypotheses"],
                        "hypotheses_id": plan.target_hypothesis_id,
                        "agent_steps": [step.model_dump(mode="json") for step in plan.execution_steps],
                        "change_reason": plan.change_reason,
                        "rollback_sql": plan.rollback_sql,
                        "risk_level": plan.risk_level,
                    }
                }
            ),
            timeout=self.MCP_TIMEOUT_S,
            label="Proposing Ticket",
            logger=logger
        )
        logger.info("%s, %s", result, fail_reason)
        if fail_reason:
            return {
                "workflow_status": WorkflowStatus.FAILED.value,
                "terminal_message": fail_reason,
            }
        if result.isError:
            error_text = result.content[0].text if result.content else "Unknown MCP tool error"
            return {
                "workflow_status": WorkflowStatus.FAILED.value,
                "terminal_message": f"propose_ticket MCP tool error: {error_text}",
            }
        logger.info("Successfully propose a ticket to TABLE change_tickets")
        return {
            "workflow_status": WorkflowStatus.PROPOSED.value,
            "ticket_id": result.content[0].text,
        }
