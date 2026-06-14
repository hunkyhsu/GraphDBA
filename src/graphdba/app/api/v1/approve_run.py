import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_202_ACCEPTED, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT

from graphdba.app.core.depends import get_current_user
from graphdba.app.schemas.request.approval import ApprovalDecision, ApprovalRequest
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
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Apply human approval and execute the staged ticket outside LangGraph."""
    try:
        alert = await alerts.get_alert_by_id(session, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Run not found") from exc
    if alert is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Run not found")
    if alert.status != AlertStatus.WAITING_APPROVAL.value:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail="Run is not waiting for approval")

    pending_ticket = await tickets.get_pending_ticket_by_alert_id(session, alert.id)
    if pending_ticket is None:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail="Run has no staged ticket")

    try:
        ticket = await tickets.approve_ticket(
            session,
            ticket_id=pending_ticket.id,
            approved_by=current_user.employee_id,
            decision=body.decision,
            modified_sql=body.modified_sql,
            approval_comments=body.feedback,
        )
        await session.commit()
        if body.decision == ApprovalDecision.REJECTED:
            reason = body.feedback or "No feedback reason provided."
            await alerts.update_alert_status(
                session,
                ticket.alert_id,
                status=AlertStatus.FAILED.value,
                failure_reason=f"Human rejected: {reason}",
            )
            await session.commit()
            return {"run_id": run_id, "status": "rejected"}

        await tickets.execute_ticket(session, ticket.id)
        await alerts.update_alert_status(
            session,
            ticket.alert_id,
            status=AlertStatus.SOLVED.value,
            solved_at=datetime.now(timezone.utc),
            clear_failure_reason=True,
        )
        await session.commit()
    except tickets.TicketNotFoundError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (tickets.TicketExecutionError, tickets.TicketStateError) as exc:
        await alerts.update_alert_status(
            session,
            alert.id,
            status=AlertStatus.FAILED.value,
            failure_reason=str(exc),
        )
        await session.commit()
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"run_id": run_id, "status": "executed"}
