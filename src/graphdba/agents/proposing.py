from __future__ import annotations
import logging
from graphdba.agents.state import WorkflowStatus
from graphdba.agents.state import AgentState, AgentStateUpdate, FinalPlan
from graphdba.database.repositories import tickets
from graphdba.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

class ProposingNode:
    """Propose the ticket about the final plan to TABLE change_tickets."""

    def __init__(self):
        pass

    async def __call__(self, state: AgentState) -> AgentStateUpdate:
        plan: FinalPlan = FinalPlan.model_validate(state["final_plan"])
        logger.info("Creating change ticket through SQLAlchemy repository...")
        try:
            async with AsyncSessionLocal() as session:
                ticket = await tickets.create_ticket_from_plan(
                    session,
                    alert_id=plan.target_alert_id,
                    target_hypothesis_id=plan.target_hypothesis_id,
                    proposed_steps=[step.model_dump(mode="json") for step in plan.execution_steps],
                    change_reason=plan.change_reason,
                    rollback_sql=plan.rollback_sql,
                    rollback_note=plan.rollback_note,
                    risk_level=plan.risk_level.value,
                )
                await session.commit()
        except Exception as exc:
            logger.exception("Failed to create change ticket")
            return {
                "workflow_status": WorkflowStatus.FAILED.value,
                "terminal_message": f"Failed to create change ticket: {exc}",
            }
        logger.info("Successfully propose a ticket to TABLE change_tickets")
        return {
            "workflow_status": WorkflowStatus.PROPOSED.value,
            "ticket_id": str(ticket.ticket_id),
        }
