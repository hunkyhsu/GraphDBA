import logging
from datetime import datetime, timezone
from langgraph.graph.state import CompiledStateGraph
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_202_ACCEPTED, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT

from graphdba.agents.state import ApprovalDecision, WorkflowStatus
from graphdba.app.core.depends import get_current_user, get_graph
from graphdba.app.schemas.request.approval import ApprovalRequest
from graphdba.app.schemas.response.approval import ApproveResponse
from graphdba.database.models.alert import AlertStatus
from graphdba.database.models.user import User
from graphdba.database.repositories import alerts, tickets
from graphdba.database.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/{run_id}/approve", status_code=HTTP_202_ACCEPTED, response_model=ApproveResponse)
async def approve_run(
    run_id: str, 
    body: ApprovalRequest,
    graph: CompiledStateGraph = Depends(get_graph),  
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Apply human approval and execute the staged ticket outside LangGraph."""
    config = {"configurable": {"thread_id": run_id}}
    state = graph.get_state(config)
    if not state.values:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Run not found")
    if state.values.get("workflow_status") != WorkflowStatus.PROPOSED.value:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail="Run is not waiting for approval")
    ticket_id = state.values.get("ticket_id")
    if not ticket_id:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail="Run has no staged ticket")
    ticket_alert_id = None
    try:
        ticket = await tickets.approve_ticket(
            session,
            ticket_id=ticket_id,
            approved_by=current_user.employee_id,
            decision=body.decision,
            modified_sql=body.modified_sql,
            approval_comments=body.feedback,
        )
        ticket_alert_id = ticket.alert_id
        await session.commit()
        if body.decision == ApprovalDecision.REJECTED:
            reason = body.feedback or "No feedback reason provided."
            await alerts.update_alert_status(
                session,
                ticket_alert_id,
                status=AlertStatus.FAILED.value,
                failure_reason=f"Human rejected: {reason}",
            )
            await session.commit()
            graph.update_state(config, {
                "approval_decision": body.decision,
                "human_feedback": body.feedback,
                "workflow_status": WorkflowStatus.COMPLETED.value,
                "terminal_message": f"Human rejected: {reason}",
            })
            return {"run_id": run_id, "status": "rejected"}

        await tickets.execute_ticket(session, ticket_id)
        await alerts.update_alert_status(
            session,
            ticket_alert_id,
            status=AlertStatus.SOLVED.value,
            solved_at=datetime.now(timezone.utc),
            clear_failure_reason=True,
        )
        await session.commit()
    except tickets.TicketNotFoundError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (tickets.TicketExecutionError, tickets.TicketStateError) as exc:
        if ticket_alert_id is not None:
            await alerts.update_alert_status(
                session,
                ticket_alert_id,
                status=AlertStatus.FAILED.value,
                failure_reason=str(exc),
            )
            await session.commit()
        graph.update_state(config, {
            "approval_decision": body.decision,
            "human_feedback": body.feedback,
            "workflow_status": WorkflowStatus.FAILED.value,
            "terminal_message": f"execute ticket failed: {exc}",
        })
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(exc)) from exc
    graph.update_state(config, {
        "approval_decision": body.decision,
        "human_feedback": body.feedback,
        "workflow_status": WorkflowStatus.COMPLETED.value,
        "terminal_message": None,
    })
    return {"run_id": run_id, "status": "executed"}
