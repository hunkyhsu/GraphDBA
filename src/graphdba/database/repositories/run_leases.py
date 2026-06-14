from datetime import datetime, timedelta, timezone
from uuid import UUID as UUIDType

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.database.models.run_lease import RunLease, RunLeaseStatus

DEFAULT_LEASE_TTL = timedelta(minutes=30)


def lease_expiry(ttl: timedelta = DEFAULT_LEASE_TTL) -> datetime:
    return datetime.now(timezone.utc) + ttl


async def get_active_lease_by_alert_id(
    session: AsyncSession,
    alert_id: UUIDType | str,
) -> RunLease | None:
    now = datetime.now(timezone.utc)
    stmt = (
        select(RunLease)
        .where(RunLease.alert_id == UUIDType(str(alert_id)))
        .where(RunLease.status == RunLeaseStatus.RUNNING.value)
        .where(RunLease.lease_expires_at > now)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def acquire_run_lease(
    session: AsyncSession,
    *,
    alert_id: UUIDType | str,
    thread_id: str,
    owner_id: str,
    ttl: timedelta = DEFAULT_LEASE_TTL,
) -> bool:
    now = datetime.now(timezone.utc)
    expires_at = now + ttl
    alert_uuid = UUIDType(str(alert_id))
    stmt = (
        insert(RunLease)
        .values(
            alert_id=alert_uuid,
            thread_id=thread_id,
            owner_id=owner_id,
            status=RunLeaseStatus.RUNNING.value,
            acquired_at=now,
            heartbeat_at=now,
            lease_expires_at=expires_at,
            released_at=None,
        )
        .on_conflict_do_update(
            index_elements=[RunLease.alert_id],
            set_={
                "thread_id": thread_id,
                "owner_id": owner_id,
                "status": RunLeaseStatus.RUNNING.value,
                "acquired_at": now,
                "heartbeat_at": now,
                "lease_expires_at": expires_at,
                "released_at": None,
            },
            where=(
                (RunLease.status != RunLeaseStatus.RUNNING.value)
                | (RunLease.lease_expires_at <= now)
            ),
        )
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount == 1


async def heartbeat_run_lease(
    session: AsyncSession,
    *,
    alert_id: UUIDType | str,
    owner_id: str,
    ttl: timedelta = DEFAULT_LEASE_TTL,
) -> bool:
    now = datetime.now(timezone.utc)
    stmt = (
        select(RunLease)
        .where(RunLease.alert_id == UUIDType(str(alert_id)))
        .where(RunLease.owner_id == owner_id)
        .where(RunLease.status == RunLeaseStatus.RUNNING.value)
        .limit(1)
    )
    result = await session.execute(stmt)
    lease = result.scalar_one_or_none()
    if lease is None:
        return False
    lease.heartbeat_at = now
    lease.lease_expires_at = now + ttl
    await session.flush()
    return True


async def release_run_lease(
    session: AsyncSession,
    *,
    alert_id: UUIDType | str,
    owner_id: str,
) -> bool:
    stmt = (
        select(RunLease)
        .where(RunLease.alert_id == UUIDType(str(alert_id)))
        .where(RunLease.owner_id == owner_id)
        .where(RunLease.status == RunLeaseStatus.RUNNING.value)
        .limit(1)
    )
    result = await session.execute(stmt)
    lease = result.scalar_one_or_none()
    if lease is None:
        return False
    lease.status = RunLeaseStatus.RELEASED.value
    lease.released_at = datetime.now(timezone.utc)
    await session.flush()
    return True
