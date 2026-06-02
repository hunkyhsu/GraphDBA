from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.app.api.v1.endpoints.alerts import _serialize_alert_list_item
from graphdba.app.api.v1.endpoints.tickets import _serialize_ticket_list_item
from graphdba.app.core.depends import get_verified_token
from graphdba.app.schemas.response.dashboard import DashboardStatsResponse
from graphdba.database.models.alert import AlertStatus
from graphdba.database.models.ticket import TicketStatus
from graphdba.database.repositories import alerts, tickets
from graphdba.database.session import get_session

router = APIRouter()


@router.get("", response_model=DashboardStatsResponse)
async def get_dashboard(
    session: AsyncSession = Depends(get_session),
    _token: dict[str, Any] = Depends(get_verified_token),
):
    alert_stats = await alerts.get_alert_stats(session)
    recent_alerts, _ = await alerts.list_alerts(session, page=1, page_size=3)
    pending_ticket_rows = await tickets.list_recent_pending_tickets(session, limit=3)
    pending_ticket_count = await tickets.count_tickets_by_status(session, TicketStatus.PENDING.value)

    distribution = [
        ("received", "Triage", await alerts.count_alerts_by_status(session, AlertStatus.RECEIVED.value)),
        ("running", "Agent Running", await alerts.count_alerts_by_status(session, AlertStatus.RUNNING.value)),
        ("waiting_approval", "Waiting Approval", alert_stats["pending_review"]),
        ("solved", "Solved", await alerts.count_alerts_by_status(session, AlertStatus.SOLVED.value)),
        ("resolved", "Resolved", await alerts.count_alerts_by_status(session, AlertStatus.RESOLVED.value)),
        ("failed", "Failed", await alerts.count_alerts_by_status(session, AlertStatus.FAILED.value)),
        ("escalated", "Escalated", await alerts.count_alerts_by_status(session, AlertStatus.ESCALATED.value)),
    ]

    return {
        "active_alerts": alert_stats["active"],
        "active_runs": alert_stats["active"] + alert_stats["pending_review"],
        "pending_approval": pending_ticket_count,
        "solved_24h": alert_stats["resolved_24h"],
        "recent_alerts": [_serialize_alert_list_item(alert) for alert in recent_alerts],
        "pending_tickets": [_serialize_ticket_list_item(ticket, alert) for ticket, alert in pending_ticket_rows],
        "run_status_distribution": [
            {"key": key, "label": label, "count": count}
            for key, label, count in distribution
        ],
    }
