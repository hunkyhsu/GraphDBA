from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.agents.container import AgentContainer
from graphdba.app.core.depends import get_agent_container
from graphdba.app.api.v1.services.alerts import ingest_firing_alerts
from graphdba.app.schemas.request.alert import AlertRequest
from graphdba.app.schemas.response.alert import (
    AlertDetailResponse,
    AlertListResponse,
    AlertStatsResponse,
    AlertsStateResponse,
)
from graphdba.database.repositories import alerts
from graphdba.database.session import get_session

router = APIRouter()

@router.get("", response_model=AlertListResponse)
async def list_alerts(
    search: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    alert_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    sort_by: str = Query(default="updated_at"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_session),
):
    items, total = await alerts.list_alerts(
        session,
        search=search,
        severity=severity,
        status=alert_status,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@router.get("/stats", response_model=AlertStatsResponse)
async def get_alert_stats(session: AsyncSession = Depends(get_session)):
    return await alerts.get_alert_stats(session)

@router.get("/{alert_id}", response_model=AlertDetailResponse)
async def get_alert_detail(alert_id: UUID, session: AsyncSession = Depends(get_session)):
    alert = await alerts.get_alert_by_id(session, alert_id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert

@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=AlertsStateResponse)
async def ingest_alerts(
    body: AlertRequest,
    background_tasks: BackgroundTasks,
    start_graph: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
    agent_container: AgentContainer = Depends(get_agent_container),
):
    run_ids = await ingest_firing_alerts(
        body=body,
        background_tasks=background_tasks,
        session=session,
        agent_container=agent_container,
        start_graph=start_graph,
    )
    return {
        "status": "accepted",
        "run_ids": run_ids
    }
