from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from graphdba.agents.state import ApprovalDecision, WorkflowStatus
from graphdba.database.repositories import tickets
from graphdba.database.session import AsyncSessionLocal

if TYPE_CHECKING:
    from graphdba.agents.state import AgentState, AgentStateUpdate

logger = logging.getLogger(__name__)

class ExecutionNode:
    def __init__(self):
        pass
    
    async def __call__(self, state: AgentState) -> AgentStateUpdate:
        decision = state["approval_decision"]
        logger.info("Human approval is %s", decision)
        if decision == ApprovalDecision.REJECTED:
            reason = state.get("human_feedback", "No feedback reason provided.")
            logger.warning("Ticket rejected by human DBA for reason: %s", reason)
            return {
                "workflow_status": WorkflowStatus.COMPLETED.value,
                "terminal_message": f"Human rejected: {reason}"
            }
        logger.info("Executing ticket through SQLAlchemy repository...")
        try:
            async with AsyncSessionLocal() as session:
                await tickets.execute_ticket(session, state["ticket_id"])
        except Exception as exc:
            logger.exception("Ticket execution failed")
            return {
                "workflow_status": WorkflowStatus.FAILED.value,
                "terminal_message": f"execute ticket failed: {exc}",
            }
        logger.info("Successfully execute a ticket to TABLE change_tickets")
        return {
            "workflow_status": WorkflowStatus.COMPLETED.value,
        }
