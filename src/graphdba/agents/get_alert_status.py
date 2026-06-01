from __future__ import annotations

import logging

from graphdba.database.repositories import alerts
from graphdba.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def get_alert_status(alert_id: str) -> tuple[str | None, str | None]:
    """Return failure reason when persistence fails; otherwise return None."""
    try:
        async with AsyncSessionLocal() as session:
            alert = await alerts.get_alert_by_id(session, alert_id)
            if alert is None:
                return None, f"Alert ID [{alert_id}] not found"
            return alert.status, None
    except Exception as exc:
        logger.exception("Failed to get alert status for %s", alert_id)
        return None, str(exc)
