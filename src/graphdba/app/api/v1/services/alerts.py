import logging
from datetime import datetime

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.agents.container import AgentContainer
from graphdba.app.api.v1.services.policy import AlertPolicyAction, apply_alert_policy
from graphdba.app.services.recovery import (
    build_agent_state,
    recover_alert_from_record,
    run_graph_with_lease,
)
from graphdba.app.schemas.request.alert import AlertItem, AlertRequest
from graphdba.database.repositories import alerts

logger = logging.getLogger(__name__)


def parse_alert_time(value: str) -> datetime | None:
    if value == "0001-01-01T00:00:00Z":
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_instance_target(instance: str | None) -> tuple[str | None, int | None]:
    if not instance:
        return None, None

    if instance.startswith("["):
        closing_bracket = instance.find("]")
        if closing_bracket == -1:
            return instance, None
        host = instance[1:closing_bracket]
        port_text = instance[closing_bracket + 1 :]
        if not port_text.startswith(":"):
            return host, None
        try:
            return host, int(port_text[1:])
        except ValueError:
            return host, None

    if ":" not in instance:
        return instance, None

    host, port_text = instance.rsplit(":", 1)
    if not host:
        return instance, None
    try:
        return host, int(port_text)
    except ValueError:
        return instance, None


def build_alert_payload_from_item(alert_id: str, alert_item: AlertItem) -> dict:
    return {
        "id": alert_id,
        "alertname": alert_item.labels.alertname,
        "instance": alert_item.labels.instance,
        "severity": alert_item.labels.severity,
        "summary": alert_item.annotations.summary,
        "description": alert_item.annotations.description or "",
        "raw_payload": alert_item.model_dump(mode="json"),
    }

async def ingest_firing_alerts(
    *,
    body: AlertRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession,
    agent_container: AgentContainer,
    start_graph: bool = True,
) -> list[str]:
    run_ids = []
    for alert_item in body.alerts:
        if alert_item.status != "firing":
            continue

        labels = alert_item.labels.model_dump(mode="json")
        annotations = alert_item.annotations.model_dump(mode="json")
        parsed_host, parsed_port = parse_instance_target(alert_item.labels.instance)
        existing_alert = await alerts.get_active_alert_by_fingerprint(session, alert_item.fingerprint)
        if existing_alert:
            run_id = str(existing_alert.id)
            logger.info("Duplicate active alert received for fingerprint %s", alert_item.fingerprint)
            if start_graph:
                graph = await agent_container.get_graph()
                background_tasks.add_task(
                    recover_alert_from_record,
                    graph=graph,
                    alert=existing_alert,
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
                host=labels.get("host") or parsed_host,
                port=labels.get("port") or parsed_port,
                environment=labels.get("environment"),
                region=labels.get("region"),
                description=alert_item.annotations.description,
                labels=labels,
                annotations=annotations,
                raw_payload=alert_item.model_dump(mode="json"),
                generator_url=alert_item.generatorURL,
                started_at=parse_alert_time(alert_item.startsAt),
                ends_at=parse_alert_time(alert_item.endsAt),
            )
            logger.info(stored_alert)
            policy_result = await apply_alert_policy(
                session,
                alert=stored_alert,
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
        if start_graph and policy_result.action == AlertPolicyAction.SLOW_PATH_AGENT:
            graph = await agent_container.get_graph()
            background_tasks.add_task(
                run_graph_with_lease,
                graph=graph,
                alert_id=run_id,
                config=config,
                initial_state=build_agent_state(
                    alert_payload=build_alert_payload_from_item(run_id, alert_item),
                ),
            )
        run_ids.append(run_id)
    return run_ids
