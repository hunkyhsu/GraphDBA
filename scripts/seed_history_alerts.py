import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.database.models.alert import Alert, AlertStatus
from graphdba.database.repositories import alerts
from graphdba.database.session import AsyncSessionLocal, engine


@dataclass(frozen=True)
class SeedAlertTemplate:
    alertname: str
    severity: str
    summary: str
    description: str


@dataclass(frozen=True)
class SeedAlertTarget:
    cluster_name: str
    database_name: str
    database_role: str
    host: str
    port: int
    environment: str
    region: str


ALERT_TEMPLATES = [
    SeedAlertTemplate(
        alertname="PostgreSQLRowLockContention",
        severity="critical",
        summary="Database row-level lock contention detected",
        description="Queries are waiting on row-level locks longer than expected.",
    ),
    SeedAlertTemplate(
        alertname="PostgreSQLLongTransaction",
        severity="warning",
        summary="Long running transaction detected",
        description="A transaction has been open long enough to risk bloat or lock pressure.",
    ),
    SeedAlertTemplate(
        alertname="PostgreSQLTooManyConnections",
        severity="warning",
        summary="Connection usage is above normal",
        description="The active connection count is approaching the configured limit.",
    ),
    SeedAlertTemplate(
        alertname="PostgreSQLDeadlocks",
        severity="critical",
        summary="Deadlocks observed in PostgreSQL",
        description="Deadlock count increased during the recent scrape window.",
    ),
    SeedAlertTemplate(
        alertname="PostgreSQLHighRollbackRate",
        severity="warning",
        summary="Rollback rate is high",
        description="The ratio of rolled-back transactions is higher than expected.",
    ),
    SeedAlertTemplate(
        alertname="PostgreSQLTableNotAutoVacuumed",
        severity="info",
        summary="Table has not been auto vacuumed recently",
        description="A table with write activity has not been auto vacuumed recently.",
    ),
    SeedAlertTemplate(
        alertname="PostgreSQLReplicationLagHigh",
        severity="critical",
        summary="Replication lag is high",
        description="Replica replay lag is above the operational threshold.",
    ),
    SeedAlertTemplate(
        alertname="PostgreSQLExporterError",
        severity="warning",
        summary="PostgreSQL exporter scrape error",
        description="The PostgreSQL exporter reported an error during metric collection.",
    ),
]


ALERT_TARGETS = [
    SeedAlertTarget(
        cluster_name="ClusterA",
        database_name="business_db_a",
        database_role="primary",
        host="127.0.0.1",
        port=5432,
        environment="DEV",
        region="local",
    ),
    SeedAlertTarget(
        cluster_name="ClusterA",
        database_name="business_db_b",
        database_role="primary",
        host="127.0.0.1",
        port=5432,
        environment="DEV",
        region="local",
    ),
    SeedAlertTarget(
        cluster_name="ClusterA",
        database_name="business_db_a",
        database_role="replica",
        host="127.0.0.1",
        port=5433,
        environment="DEV",
        region="local",
    ),
]


STATUS_SEQUENCE = [
    AlertStatus.RECEIVED.value,
    AlertStatus.RUNNING.value,
    AlertStatus.WAITING_APPROVAL.value,
    AlertStatus.SOLVED.value,
    AlertStatus.RESOLVED.value,
    AlertStatus.FAILED.value,
    AlertStatus.ESCALATED.value,
]


def build_labels(
    *,
    template: SeedAlertTemplate,
    target: SeedAlertTarget,
    status: str,
) -> dict[str, str]:
    return {
        "alertname": template.alertname,
        "cluster_name": target.cluster_name,
        "database_name": target.database_name,
        "database_role": target.database_role,
        "datname": target.database_name,
        "environment": target.environment,
        "host": target.host,
        "instance": f"{target.host}:{target.port}",
        "job": "postgres-cluster",
        "port": str(target.port),
        "region": target.region,
        "server": f"{target.host}:{target.port}",
        "severity": template.severity,
        "state": "resolved" if status in {AlertStatus.SOLVED.value, AlertStatus.RESOLVED.value} else "active",
    }


def build_raw_payload(
    *,
    fingerprint: str,
    template: SeedAlertTemplate,
    target: SeedAlertTarget,
    labels: dict[str, str],
    annotations: dict[str, str],
    starts_at: datetime,
    ends_at: datetime | None,
    status: str,
) -> dict[str, object]:
    alertmanager_status = "resolved" if status in {AlertStatus.SOLVED.value, AlertStatus.RESOLVED.value} else "firing"
    ends_at_value = ends_at.isoformat().replace("+00:00", "Z") if ends_at else "0001-01-01T00:00:00Z"
    starts_at_value = starts_at.isoformat().replace("+00:00", "Z")

    return {
        "status": alertmanager_status,
        "labels": labels,
        "annotations": annotations,
        "startsAt": starts_at_value,
        "endsAt": ends_at_value,
        "generatorURL": (
            "http://localhost:9090/graph"
            f"?g0.expr={template.alertname}&g0.tab=1"
        ),
        "fingerprint": fingerprint,
        "target": {
            "cluster_name": target.cluster_name,
            "database_name": target.database_name,
            "database_role": target.database_role,
        },
    }


async def upsert_seed_alert(
    session: AsyncSession,
    *,
    index: int,
    now: datetime,
) -> None:
    template = ALERT_TEMPLATES[index % len(ALERT_TEMPLATES)]
    target = ALERT_TARGETS[index % len(ALERT_TARGETS)]
    status = STATUS_SEQUENCE[index % len(STATUS_SEQUENCE)]
    fingerprint = f"seed-history-alert-{index + 1:03d}"
    starts_at = now - timedelta(minutes=(index + 1) * 17)
    updated_at = starts_at + timedelta(minutes=3 + (index % 9))
    ends_at = None
    solved_at = None
    resolved_at = None

    if status in {AlertStatus.SOLVED.value, AlertStatus.RESOLVED.value}:
        ends_at = updated_at
        resolved_at = updated_at
        solved_at = updated_at
    elif status == AlertStatus.FAILED.value:
        ends_at = updated_at
    elif status == AlertStatus.ESCALATED.value:
        ends_at = updated_at

    labels = build_labels(template=template, target=target, status=status)
    annotations = {
        "summary": template.summary,
        "description": template.description,
    }
    raw_payload = build_raw_payload(
        fingerprint=fingerprint,
        template=template,
        target=target,
        labels=labels,
        annotations=annotations,
        starts_at=starts_at,
        ends_at=ends_at,
        status=status,
    )

    result = await session.execute(
        select(Alert).where(Alert.fingerprint == fingerprint).limit(1)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        alert = await alerts.create_alert(
            session,
            fingerprint=fingerprint,
            alertname=template.alertname,
            instance=labels["instance"],
            severity=template.severity,
            alert_summary=template.summary,
            cluster_name=target.cluster_name,
            database_name=target.database_name,
            database_role=target.database_role,
            host=target.host,
            port=target.port,
            environment=target.environment,
            region=target.region,
            description=template.description,
            labels=labels,
            annotations=annotations,
            raw_payload=raw_payload,
            generator_url=str(raw_payload["generatorURL"]),
            started_at=starts_at,
            ends_at=ends_at,
        )
    else:
        alert.name = template.alertname
        alert.instance = labels["instance"]
        alert.severity = template.severity
        alert.summary = template.summary
        alert.cluster_name = target.cluster_name
        alert.database_name = target.database_name
        alert.database_role = target.database_role
        alert.host = target.host
        alert.port = target.port
        alert.environment = target.environment
        alert.region = target.region
        alert.description = template.description
        alert.labels = labels
        alert.annotations = annotations
        alert.raw_payload = raw_payload
        alert.generator_url = str(raw_payload["generatorURL"])
        alert.started_at = starts_at
        alert.ends_at = ends_at

    alert.status = status
    alert.received_at = starts_at
    alert.updated_at = updated_at
    alert.last_seen_at = updated_at
    alert.solved_at = solved_at
    alert.resolved_at = resolved_at
    alert.occurrence_count = 1 + (index % 4)
    alert.failure_reason = "Seeded failure for frontend history display." if status == AlertStatus.FAILED.value else None
    alert.escalation_reason = "Seeded escalation for frontend history display." if status == AlertStatus.ESCALATED.value else None
    if not alert.thread_id:
        alert.thread_id = str(alert.id)


async def seed_history_alerts() -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        for index in range(36):
            await upsert_seed_alert(session, index=index, now=now)
        await session.commit()


async def main() -> None:
    try:
        await seed_history_alerts()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
