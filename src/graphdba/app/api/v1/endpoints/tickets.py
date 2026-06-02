from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.app.core.depends import get_verified_token
from graphdba.app.schemas.request.ticket import TicketPlanUpdateRequest
from graphdba.app.schemas.response.ticket import TicketDetailResponse, TicketListResponse
from graphdba.database.models.alert import Alert
from graphdba.database.models.hypothesis import HypothesisRecord
from graphdba.database.models.ticket import Ticket
from graphdba.database.repositories import hypotheses, tickets
from graphdba.database.session import get_session

router = APIRouter()


def _serialize_ticket_list_item(ticket: Ticket, alert: Alert) -> dict:
    return {
        "ticket_id": ticket.id,
        "alert_id": ticket.alert_id,
        "run_id": alert.thread_id or str(alert.id),
        "alertname": alert.name,
        "instance": alert.instance,
        "status": ticket.status,
        "risk_level": ticket.risk_level,
        "change_reason": ticket.change_reason,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


def _serialize_hypothesis(hypothesis: HypothesisRecord) -> dict[str, Any]:
    return {
        "hypothesis_id": hypothesis.hypothesis_id,
        "root_cause": hypothesis.root_cause,
        "status": hypothesis.status,
        "confidence_score": hypothesis.confidence_score,
        "feedback": hypothesis.feedback,
        "metric_evidence": hypothesis.metric_evidence,
    }


def _serialize_ticket_detail(
    ticket: Ticket,
    alert: Alert,
    ticket_hypotheses: list[HypothesisRecord],
) -> dict:
    return {
        "ticket_id": ticket.id,
        "alert_id": ticket.alert_id,
        "run_id": alert.thread_id or str(alert.id),
        "hypothesis_id": ticket.hypothesis_id,
        "status": ticket.status,
        "risk_level": ticket.risk_level,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "proposed_steps": ticket.proposed_steps,
        "approved_steps": ticket.approved_steps,
        "change_reason": ticket.change_reason,
        "rollback_sql": ticket.rollback_sql,
        "rollback_note": ticket.rollback_note,
        "approved_by": ticket.approved_by,
        "approved_at": ticket.approved_at,
        "approval_comments": ticket.approval_comments,
        "executed_at": ticket.executed_at,
        "execution_duration_ms": ticket.execution_duration_ms,
        "error_message": ticket.error_message,
        "metadata": ticket.metadata_,
        "alert": {
            "alert_id": alert.id,
            "alertname": alert.name,
            "severity": alert.severity,
            "status": alert.status,
            "instance": alert.instance,
            "cluster_name": alert.cluster_name,
            "database_name": alert.database_name,
            "database_role": alert.database_role,
            "summary": alert.summary,
            "started_at": alert.started_at,
            "updated_at": alert.updated_at,
            "thread_id": alert.thread_id,
        },
        "hypotheses": [_serialize_hypothesis(hypothesis) for hypothesis in ticket_hypotheses],
    }


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    search: str | None = Query(default=None),
    ticket_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    sort_by: str = Query(default="updated_at"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_session),
    _token: dict[str, Any] = Depends(get_verified_token),
):
    rows, total = await tickets.list_tickets(
        session,
        search=search,
        status=ticket_status,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return {
        "items": [_serialize_ticket_list_item(ticket, alert) for ticket, alert in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{ticket_id}", response_model=TicketDetailResponse)
async def get_ticket_detail(
    ticket_id: UUID,
    session: AsyncSession = Depends(get_session),
    _token: dict[str, Any] = Depends(get_verified_token),
):
    row = await tickets.get_ticket_with_alert(session, ticket_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    ticket, alert = row
    ticket_hypotheses = await hypotheses.list_hypotheses_for_alert(session, alert.id)
    return _serialize_ticket_detail(ticket, alert, ticket_hypotheses)


@router.put("/{ticket_id}/plan", response_model=TicketDetailResponse)
async def update_ticket_plan(
    ticket_id: UUID,
    body: TicketPlanUpdateRequest,
    session: AsyncSession = Depends(get_session),
    _token: dict[str, Any] = Depends(get_verified_token),
):
    try:
        await tickets.update_ticket_plan(
            session,
            ticket_id=ticket_id,
            proposed_steps=[step.model_dump(mode="json") for step in body.proposed_steps],
            change_reason=body.change_reason,
            rollback_sql=body.rollback_sql,
            rollback_note=body.rollback_note,
            human_notes=body.human_notes,
            pre_execution_notes=body.pre_execution_notes,
        )
        await session.commit()
    except tickets.TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (tickets.TicketExecutionError, tickets.TicketStateError) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    row = await tickets.get_ticket_with_alert(session, ticket_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    ticket, alert = row
    ticket_hypotheses = await hypotheses.list_hypotheses_for_alert(session, alert.id)
    return _serialize_ticket_detail(ticket, alert, ticket_hypotheses)
