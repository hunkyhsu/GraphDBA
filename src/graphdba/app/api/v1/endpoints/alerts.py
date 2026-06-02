import logging
import re
from datetime import datetime, timezone
from uuid import UUID
from langgraph.graph.state import CompiledStateGraph
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.agents.state import FinalPlan, WorkflowStatus
from graphdba.app.core.depends import get_graph
from graphdba.app.schemas.request.alert import AlertItem, AlertRequest
from graphdba.app.schemas.response.alert import (
    AlertDetailResponse,
    AlertListResponse,
    AlertStatsResponse,
    AlertsStateResponse,
)
from graphdba.database.models.alert import Alert, AlertStatus
from graphdba.database.repositories import alerts, tickets
from graphdba.database.session import AsyncSessionLocal, get_session

logger = logging.getLogger(__name__)
router = APIRouter()

PHYSICAL_KEYWORDS_PATTERN = re.compile(
    r"corruption|bad block|segfault|oom|out of memory|disk full|storage offline|network unreachable|pg_down",
    re.IGNORECASE,
)
FAST_PATH_SCRIPT_ALERTS = {
    "PostgreSQLConnectionsExhausted",
}

async def _run_graph(graph: CompiledStateGraph, initial_state: dict, config: dict):
    try:
        if graph.get_state(config=config).values:
            # same request
            logger.info("Duplicate alert ignored for thread %s", config["configurable"]["thread_id"])
            return 
        async for _ in graph.astream(initial_state, config):
            pass
        await _propose_ticket_if_planned(graph, config)
    except Exception:
        logger.exception("Graph run failed for thread %s", config["configurable"]["thread_id"])

def _parse_alert_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def _build_agent_state(
    *,
    alert_payload: dict,
    workflow_status: WorkflowStatus,
    terminal_message: str | None = None,
) -> dict:
    return {
        "alert": alert_payload,
        "current_hypotheses": [],
        "rejected_hypotheses": [],
        "final_plan": None,
        "ticket_id": None,
        "attempt_count": 0,
        "workflow_status": workflow_status.value,
        "approval_decision": None,
        "human_feedback": None,
        "terminal_message": terminal_message,
    }

def _build_alert_payload_from_item(alert_id: str, alert_item: AlertItem) -> dict:
    return {
        "id": alert_id,
        "alertname": alert_item.labels.alertname,
        "instance": alert_item.labels.instance,
        "severity": alert_item.labels.severity,
        "summary": alert_item.annotations.summary,
        "description": alert_item.annotations.description or "",
        "raw_payload": alert_item.model_dump(mode="json"),
    }

def _build_alert_payload_from_record(alert: Alert) -> dict:
    return {
        "id": str(alert.id),
        "alertname": alert.name,
        "instance": alert.instance or "",
        "severity": alert.severity,
        "summary": alert.summary,
        "description": alert.description or "",
        "raw_payload": alert.raw_payload,
    }

async def _apply_alert_policy(
    session: AsyncSession,
    *,
    alert: Alert,
    alert_item: AlertItem,
) -> tuple[WorkflowStatus, str | None]:
    alert_name = alert_item.labels.alertname
    alert_description = alert_item.annotations.description or ""

    if alert_name in FAST_PATH_SCRIPT_ALERTS:
        logger.info("Fast path script triggered for alert %s", alert_name)
        # The current fast path is represented by persisted status only. Actual
        # script execution should stay in the FastAPI orchestration layer.
        await alerts.update_alert_status(
            session,
            alert.id,
            status=AlertStatus.SOLVED.value,
            solved_at=datetime.now(timezone.utc),
            clear_failure_reason=True,
        )
        return WorkflowStatus.COMPLETED, "Executed fast path script successfully"

    is_physical_error = bool(
        PHYSICAL_KEYWORDS_PATTERN.search(alert_description)
        or PHYSICAL_KEYWORDS_PATTERN.search(alert_name)
    )
    if is_physical_error:
        reason = f"Detected physical error for {alert_name}, required human DBA"
        logger.error("Fast path escalation triggered for alert %s", alert_name)
        await alerts.update_alert_status(
            session,
            alert.id,
            status=AlertStatus.ESCALATED.value,
            escalation_reason=reason,
            clear_failure_reason=True,
        )
        return WorkflowStatus.ESCALATED, reason

    await alerts.update_alert_status(
        session,
        alert.id,
        status=AlertStatus.RUNNING.value,
        clear_failure_reason=True,
    )
    return WorkflowStatus.TRIAGED, None

async def _propose_ticket_if_planned(graph: CompiledStateGraph, config: dict) -> None:
    state = graph.get_state(config=config)
    if state.values.get("workflow_status") != WorkflowStatus.PLANNED.value:
        return

    try:
        plan = FinalPlan.model_validate(state.values["final_plan"])
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
            await alerts.update_alert_status(
                session,
                plan.target_alert_id,
                status=AlertStatus.WAITING_APPROVAL.value,
                clear_failure_reason=True,
            )
            await session.commit()
    except Exception as exc:
        logger.exception("Failed to create change ticket for thread %s", config["configurable"]["thread_id"])
        graph.update_state(config, {
            "workflow_status": WorkflowStatus.FAILED.value,
            "terminal_message": f"Failed to create change ticket: {exc}",
        })
        try:
            alert_id = state.values.get("alert", {}).get("id")
            if alert_id:
                async with AsyncSessionLocal() as session:
                    await alerts.update_alert_status(
                        session,
                        alert_id,
                        status=AlertStatus.FAILED.value,
                        failure_reason=f"Failed to create change ticket: {exc}",
                    )
                    await session.commit()
        except Exception:
            logger.exception("Failed to persist alert failure after ticket proposal error")
        return

    graph.update_state(config, {
        "workflow_status": WorkflowStatus.PROPOSED.value,
        "ticket_id": str(ticket.id),
    })
    logger.info("Created change ticket %s for thread %s", ticket.id, config["configurable"]["thread_id"])

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
        "alert_id": alert.id,
        "alertname": alert.name,
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
            run_id = str(existing_alert.id)
            config = {"configurable": {"thread_id": run_id}}
            existing_state = graph.get_state(config=config)
            if existing_state.values:
                if (
                    existing_state.values.get("workflow_status") == WorkflowStatus.PLANNED.value
                    and not existing_state.values.get("ticket_id")
                ):
                    logger.info("Recovering ticket proposal for fingerprint %s", alert_item.fingerprint)
                    background_tasks.add_task(
                        _propose_ticket_if_planned,
                        graph=graph,
                        config=config,
                    )
                else:
                    logger.info("Duplicate active alert ignored for fingerprint %s", alert_item.fingerprint)
            elif existing_alert.status in (AlertStatus.RECEIVED.value, AlertStatus.RUNNING.value):
                logger.info("Recovering active alert graph for fingerprint %s", alert_item.fingerprint)
                workflow_status = WorkflowStatus.TRIAGED
                terminal_message = None
                if existing_alert.status == AlertStatus.RECEIVED.value:
                    workflow_status, terminal_message = await _apply_alert_policy(
                        session,
                        alert=existing_alert,
                        alert_item=alert_item,
                    )
                    await session.commit()
                background_tasks.add_task(
                    _run_graph,
                    graph=graph,
                    initial_state=_build_agent_state(
                        alert_payload=_build_alert_payload_from_record(existing_alert),
                        workflow_status=workflow_status,
                        terminal_message=terminal_message,
                    ),
                    config=config,
                )
            else:
                logger.info(
                    "Active alert has no recoverable graph checkpoint for fingerprint %s and status %s",
                    alert_item.fingerprint,
                    existing_alert.status,
                )
            run_ids.append(run_id)
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
                database_name=labels.get("database_name") or labels.get("datname"),
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
            workflow_status, terminal_message = await _apply_alert_policy(
                session,
                alert=stored_alert,
                alert_item=alert_item,
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
        background_tasks.add_task(
            _run_graph,
            graph=graph,
            initial_state=_build_agent_state(
                alert_payload=_build_alert_payload_from_item(run_id, alert_item),
                workflow_status=workflow_status,
                terminal_message=terminal_message,
            ),
            config=config,
        )
        run_ids.append(run_id)
    return {
        "status": "accepted",
        "run_ids": run_ids
    }
