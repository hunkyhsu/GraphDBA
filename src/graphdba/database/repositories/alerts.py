from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.database.models.alert import Alert, AlertStatus


class AlertConflictError(Exception):
    """Raised when an active alert already exists for the same fingerprint."""


ACTIVE_STATUSES = (
    AlertStatus.RECEIVED.value,
    AlertStatus.RUNNING.value,
)
TERMINAL_STATUSES = (
    AlertStatus.SOLVED.value,
    AlertStatus.RESOLVED.value,
    AlertStatus.FAILED.value,
    AlertStatus.ESCALATED.value,
)

ALERT_SORT_COLUMNS = {
    "alertname": Alert.name,
    "severity": Alert.severity,
    "status": Alert.status,
    "started_at": Alert.started_at,
    "updated_at": Alert.updated_at,
    "received_at": Alert.received_at,
}


def _normalize_status_filter(status: str | None) -> list[str] | None:
    if not status or status.lower() == "all":
        return None
    status_key = status.lower()
    if status_key == "active":
        return list(ACTIVE_STATUSES)
    if status_key == "pending":
        return [AlertStatus.WAITING_APPROVAL.value]
    if status_key == "resolved":
        return [AlertStatus.SOLVED.value, AlertStatus.RESOLVED.value]
    return [status.upper()]


def _apply_alert_filters(
    stmt: Select[tuple[Alert]] | Select[tuple[int]],
    *,
    search: str | None = None,
    severity: str | None = None,
    status: str | None = None,
):
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Alert.name.ilike(pattern),
                Alert.instance.ilike(pattern),
                Alert.summary.ilike(pattern),
                Alert.cluster_name.ilike(pattern),
                Alert.database_name.ilike(pattern),
            )
        )
    if severity and severity.lower() != "all":
        stmt = stmt.where(func.lower(Alert.severity) == severity.lower())
    status_values = _normalize_status_filter(status)
    if status_values:
        stmt = stmt.where(Alert.status.in_(status_values))
    return stmt


async def get_alert_by_id(session: AsyncSession, alert_id: UUIDType | str) -> Alert | None:
    return await session.get(Alert, UUIDType(str(alert_id)))


async def get_active_alert_by_fingerprint(
    session: AsyncSession,
    fingerprint: str,
) -> Alert | None:
    stmt = (
        select(Alert)
        .where(Alert.fingerprint == fingerprint)
        .where(Alert.status.not_in(TERMINAL_STATUSES))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_alert(
    session: AsyncSession,
    *,
    fingerprint: str,
    alertname: str,
    severity: str,
    alert_summary: str,
    instance: str | None = None,
    cluster_name: str | None = None,
    database_name: str | None = None,
    database_role: str | None = None,
    host: str | None = None,
    port: int | None = None,
    environment: str | None = None,
    region: str | None = None,
    description: str | None = None,
    labels: dict[str, Any] | None = None,
    annotations: dict[str, Any] | None = None,
    raw_payload: dict[str, Any] | None = None,
    generator_url: str | None = None,
    started_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> Alert:
    alert = Alert(
        fingerprint=fingerprint,
        name=alertname,
        severity=severity,
        instance=instance,
        cluster_name=cluster_name,
        database_name=database_name,
        database_role=database_role,
        host=host,
        port=port,
        environment=environment,
        region=region,
        summary=alert_summary,
        description=description,
        labels=labels or {},
        annotations=annotations or {},
        raw_payload=raw_payload or {},
        generator_url=generator_url,
        started_at=started_at,
        ends_at=ends_at,
        last_seen_at=started_at,
    )
    session.add(alert)
    try:
        await session.flush()
        alert.thread_id = str(alert.id)
        await session.flush()
    except IntegrityError as exc:
        raise AlertConflictError(f"Alert already exists for fingerprint: {fingerprint}") from exc
    return alert


async def update_alert_status(
    session: AsyncSession,
    alert_id: UUIDType | str,
    *,
    status: str,
    failure_reason: str | None = None,
    escalation_reason: str | None = None,
    solved_at: datetime | None = None,
    resolved_at: datetime | None = None,
    clear_failure_reason: bool = False,
) -> Alert | None:
    alert_uuid = UUIDType(str(alert_id))
    alert = await session.get(Alert, alert_uuid)
    if alert is None:
        return None
    if alert.status in TERMINAL_STATUSES:
        return alert

    alert.status = status
    if escalation_reason is not None:
        alert.escalation_reason = escalation_reason
    if solved_at is not None:
        alert.solved_at = solved_at
    if resolved_at is not None:
        alert.resolved_at = resolved_at
    if clear_failure_reason:
        alert.failure_reason = None
    elif failure_reason is not None:
        alert.failure_reason = failure_reason
    await session.flush()
    return alert


async def list_alerts(
    session: AsyncSession,
    *,
    search: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
) -> tuple[list[Alert], int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size

    count_stmt = _apply_alert_filters(
        select(func.count()).select_from(Alert),
        search=search,
        severity=severity,
        status=status,
    )
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    sort_column = ALERT_SORT_COLUMNS.get(sort_by, Alert.updated_at)
    order_column = sort_column.asc() if sort_dir.lower() == "asc" else sort_column.desc()
    list_stmt = _apply_alert_filters(
        select(Alert),
        search=search,
        severity=severity,
        status=status,
    ).order_by(order_column, Alert.id.desc()).limit(page_size).offset(offset)

    result = await session.execute(list_stmt)
    return list(result.scalars().all()), total


async def get_alert_stats(session: AsyncSession) -> dict[str, int]:
    resolved_since = datetime.now(timezone.utc) - timedelta(hours=24)
    stmt = select(
        func.count()
        .filter(Alert.status.in_(ACTIVE_STATUSES))
        .label("active"),
        func.count()
        .filter(func.lower(Alert.severity) == "critical")
        .filter(Alert.status.not_in(TERMINAL_STATUSES))
        .label("critical"),
        func.count()
        .filter(Alert.status == AlertStatus.WAITING_APPROVAL.value)
        .label("pending_review"),
        func.count()
        .filter(Alert.status.in_((AlertStatus.SOLVED.value, AlertStatus.RESOLVED.value)))
        .filter(func.coalesce(Alert.resolved_at, Alert.solved_at, Alert.updated_at) >= resolved_since)
        .label("resolved_24h"),
    )
    result = await session.execute(stmt)
    row = result.one()
    return {
        "active": row.active,
        "critical": row.critical,
        "pending_review": row.pending_review,
        "resolved_24h": row.resolved_24h,
    }


async def count_alerts_by_status(session: AsyncSession, status: str) -> int:
    result = await session.execute(select(func.count()).select_from(Alert).where(Alert.status == status))
    return result.scalar_one()
