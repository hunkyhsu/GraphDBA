import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from graphdba.database.base import Base

if TYPE_CHECKING:
    from graphdba.database.models.alert import Alert


class TicketStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class TicketRiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    hypothesis_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    proposed_steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    approved_steps: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
    )
    change_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    rollback_sql: Mapped[str | None] = mapped_column(
        Text,
    )
    rollback_note: Mapped[str | None] = mapped_column(
        Text,
    )
    risk_level: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    approved_by: Mapped[str | None] = mapped_column(
        Text,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    approval_comments: Mapped[str | None] = mapped_column(
        Text,
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    execution_duration_ms: Mapped[int | None] = mapped_column(
        Integer,
    )
    rolled_back_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=TicketStatus.PENDING.value,
        server_default=text("'PENDING'"),
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    alert: Mapped["Alert"] = relationship()

    __table_args__ = (
        CheckConstraint(
            risk_level.in_([risk.value for risk in TicketRiskLevel]),
            name="ck_change_tickets_risk_level",
        ),
        CheckConstraint(
            status.in_([status.value for status in TicketStatus]),
            name="ck_change_tickets_status",
        ),
    )
