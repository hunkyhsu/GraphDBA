from __future__ import annotations

import logging
from datetime import datetime

from graphdba.database.repositories import alerts
from graphdba.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def update_alert(
    alert_id: str,
    status: str,
    failure_reason: str | None = None,
    escalation_reason: str | None = None,
    solved_at: str | datetime | None = None,
    resolved_at: str | datetime | None = None,
    clear_failure_reason: bool = False,
) -> str | None:
    """Return failure reason when persistence fails; otherwise return None."""
    try:
        async with AsyncSessionLocal() as session:
            alert = await alerts.update_alert_status(
                session,
                alert_id,
                status=status,
                failure_reason=failure_reason,
                escalation_reason=escalation_reason,
                solved_at=_parse_datetime(solved_at),
                resolved_at=_parse_datetime(resolved_at),
                clear_failure_reason=clear_failure_reason,
            )
            if alert is None:
                return f"Alert ID [{alert_id}] not found"
            await session.commit()
        return None
    except Exception as exc:
        logger.exception("Failed to update alert %s to %s", alert_id, status)
        return str(exc)
