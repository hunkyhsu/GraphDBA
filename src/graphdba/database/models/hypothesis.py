from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from graphdba.database.base import Base


class HypothesisStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class HypothesisRecord(Base):
    __tablename__ = "hypotheses"

    hypothesis_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )
    alert_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("alerts.alert_id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    root_cause: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    validation_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    expected_result: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=HypothesisStatus.PENDING.value,
        server_default=text("'pending'"),
    )
    feedback: Mapped[str | None] = mapped_column(
        Text,
    )
    metric_evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    __table_args__ = (
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_hypotheses_confidence_score",
        ),
        CheckConstraint(
            status.in_([status.value for status in HypothesisStatus]),
            name="ck_hypotheses_status",
        ),
    )
