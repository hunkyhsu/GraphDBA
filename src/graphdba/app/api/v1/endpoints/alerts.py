import logging
from datetime import datetime
from uuid import UUID
from langgraph.graph.state import CompiledStateGraph
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.app.core.depends import get_graph
from graphdba.app.schemas.request.alert import AlertItem, AlertRequest
from graphdba.app.schemas.response.alert import (
    AlertDetailResponse,
    AlertListResponse,
    AlertStatsResponse,
    AlertsStateResponse,
)
from graphdba.database.models.alert import Alert
from graphdba.database.repositories import alerts
from graphdba.database.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter()

async def _run_graph(graph: CompiledStateGraph, initial_state: dict, config: dict):
    try:
        if graph.get_state(config=config).values:
            # same request
            logger.info("Duplicate alert ignored for thread %s", config["configurable"]["thread_id"])
            return 
        async for _ in graph.astream(initial_state, config):
            pass
    except Exception:
        logger.exception("Graph run failed for thread %s", config["configurable"]["thread_id"])

def _parse_alert_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def _serialize_alert(alert: Alert) -> dict:
    return {
        "alert_id": alert.id,
        "fingerprint": alert.fingerprint,
        "alertname": alert.name,
        "severity": alert.severity,
        "status": alert.status,
        "instance": alert.instance,
        "cluster_name": alert.cluster_name,
        "database_name": alert.database_name,
        "database_role": alert.database_role,
        "host": alert.host,
        "port": alert.port,
        "environment": alert.environment,
        "region": alert.region,
        "alert_summary": alert.summary,
        "description": alert.description,
        "labels": alert.labels,
        "annotations": alert.annotations,
        "raw_payload": alert.raw_payload,
        "generator_url": alert.generator_url,
        "started_at": alert.started_at,
        "ends_at": alert.ends_at,
        "received_at": alert.received_at,
        "updated_at": alert.updated_at,
        "last_seen_at": alert.last_seen_at,
        "resolved_at": alert.resolved_at,
        "occurrence_count": alert.occurrence_count,
        "thread_id": alert.thread_id,
        "escalation_reason": alert.escalation_reason,
        "failure_reason": alert.failure_reason,
    }

def _serialize_alert_list_item(alert: Alert) -> dict:
    return {
        "alert_id": alert.alert_id,
        "alertname": alert.alertname,
        "severity": alert.severity,
        "status": alert.status,
        "instance": alert.instance,
        "cluster_name": alert.cluster_name,
        "database_name": alert.database_name,
        "database_role": alert.database_role,
        "started_at": alert.started_at,
        "updated_at": alert.updated_at,
    }

@router.get("", response_model=AlertListResponse)
async def list_alerts(
    search: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    alert_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
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
        "items": [_serialize_alert_list_item(alert) for alert in items],
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
    return _serialize_alert(alert)

@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=AlertsStateResponse)
async def ingest_alerts(
    body: AlertRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    graph: CompiledStateGraph = Depends(get_graph),
):
    run_ids = []
    for alert_item in body.alerts:
        if alert_item.status != "firing":
            continue

        labels = alert_item.labels.model_dump(mode="json")
        annotations = alert_item.annotations.model_dump(mode="json")
        existing_alert = await alerts.get_active_alert_by_fingerprint(session, alert_item.fingerprint)
        if existing_alert:
            logger.info("Duplicate active alert ignored for fingerprint %s", alert_item.fingerprint)
            run_ids.append(str(existing_alert.id))
            continue

        try:
            stored_alert = await alerts.create_alert(
                session,
                fingerprint=alert_item.fingerprint,
                alertname=alert_item.labels.alertname,
                instance=alert_item.labels.instance,
                severity=alert_item.labels.severity,
                alert_summary=alert_item.annotations.summary,
                cluster_name=labels.get("cluster_name"),
                database_name=labels.get("database_name"),
                database_role=labels.get("database_role"),
                host=labels.get("host"),
                port=labels.get("port"),
                environment=labels.get("environment"),
                region=labels.get("region"),
                description=alert_item.annotations.description,
                labels=labels,
                annotations=annotations,
                raw_payload=alert_item.model_dump(mode="json"),
                generator_url=alert_item.generatorURL,
                started_at=_parse_alert_time(alert_item.startsAt),
                ends_at=_parse_alert_time(alert_item.endsAt),
            )
            await session.commit()
        except alerts.AlertConflictError:
            await session.rollback()
            existing_alert = await alerts.get_active_alert_by_fingerprint(session, alert_item.fingerprint)
            if existing_alert:
                logger.info("Concurrent duplicate active alert ignored for fingerprint %s", alert_item.fingerprint)
                run_ids.append(str(existing_alert.id))
                continue
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Alert already exists") from None

        run_id = str(stored_alert.id)

        config = {"configurable": {"thread_id": run_id}}
        alert_payload = {
            "id": run_id,
            "alertname": alert_item.labels.alertname,
            "instance": alert_item.labels.instance,
            "severity": alert_item.labels.severity,
            "summary": alert_item.annotations.summary,
            "description": alert_item.annotations.description or "",
            "raw_payload": alert_item.model_dump(mode="json"),
        }
        background_tasks.add_task(
            _run_graph,
            graph=graph,
            initial_state={"alert": alert_payload},
            config=config,
        )
        run_ids.append(run_id)
    return {
        "status": "accepted",
        "run_ids": run_ids
    }
