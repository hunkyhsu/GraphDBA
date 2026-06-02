from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from graphdba.database.models.hypothesis import HypothesisRecord


async def upsert_hypotheses(
    session: AsyncSession,
    *,
    alert_id: UUID | str,
    attempt_count: int,
    hypotheses: list[dict],
) -> None:
    if not hypotheses:
        return

    now = datetime.now(timezone.utc)
    rows = []
    for hypothesis in hypotheses:
        rows.append(
            {
                "hypothesis_id": hypothesis["id"],
                "alert_id": UUID(str(alert_id)),
                "attempt_count": attempt_count,
                "root_cause": hypothesis["root_cause"],
                "confidence_score": hypothesis["confidence_score"],
                "validation_actions": hypothesis["validation_actions"],
                "expected_result": hypothesis["expected_result"],
                "status": hypothesis["status"],
                "feedback": hypothesis.get("feedback"),
                "validated_at": now if hypothesis["status"] != "pending" else None,
            }
        )

    stmt = insert(HypothesisRecord).values(rows)
    update_columns = {
        "attempt_count": stmt.excluded.attempt_count,
        "root_cause": stmt.excluded.root_cause,
        "confidence_score": stmt.excluded.confidence_score,
        "validation_actions": stmt.excluded.validation_actions,
        "expected_result": stmt.excluded.expected_result,
        "status": stmt.excluded.status,
        "feedback": stmt.excluded.feedback,
        "validated_at": stmt.excluded.validated_at,
    }
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[HypothesisRecord.hypothesis_id],
            set_=update_columns,
        )
    )
    await session.flush()


async def list_hypotheses_for_alert(
    session: AsyncSession,
    alert_id: UUID | str,
) -> list[HypothesisRecord]:
    stmt = (
        select(HypothesisRecord)
        .where(HypothesisRecord.alert_id == UUID(str(alert_id)))
        .order_by(HypothesisRecord.attempt_count.asc(), HypothesisRecord.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
