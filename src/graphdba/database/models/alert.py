import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from graphdba.database.base import Base


class AlertStatus(StrEnum):
    RECEIVED = "RECEIVED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SOLVED = "SOLVED"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"


class DatabaseRole(StrEnum):
    PRIMARY = "primary"
    REPLICA = "replica"


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    fingerprint: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    instance: Mapped[str | None] = mapped_column(
        Text,
    )
    cluster_name: Mapped[str | None] = mapped_column(
        Text,
    )
    database_name: Mapped[str | None] = mapped_column(
        Text,
    )
    database_role: Mapped[str | None] = mapped_column(
        Text,
    )
    host: Mapped[str | None] = mapped_column(
        Text,
    )
    port: Mapped[int | None] = mapped_column(
        Integer,
    )
    environment: Mapped[str | None] = mapped_column(
        Text,
    )
    region: Mapped[str | None] = mapped_column(
        Text,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
    )
    labels: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    annotations: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    generator_url: Mapped[str | None] = mapped_column(
        Text,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=AlertStatus.RECEIVED.value,
        server_default=text("'RECEIVED'"),
    )
    escalation_reason: Mapped[str | None] = mapped_column(
        Text,
    )
    failure_reason: Mapped[str | None] = mapped_column(
        Text,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    received_at: Mapped[datetime] = mapped_column(
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
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    solved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    occurrence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    thread_id: Mapped[str | None] = mapped_column(
        Text,
    )

    __table_args__ = (
        CheckConstraint(
            status.in_([status.value for status in AlertStatus]),
            name="ck_alerts_status",
        ),
        CheckConstraint(
            database_role.in_([role.value for role in DatabaseRole]),
            name="ck_alerts_database_role",
        ),
        Index(
            "idx_alerts_unique_active_fingerprint",
            "fingerprint",
            unique=True,
            postgresql_where=status.not_in(
                [
                    AlertStatus.SOLVED.value,
                    AlertStatus.RESOLVED.value,
                    AlertStatus.FAILED.value,
                    AlertStatus.ESCALATED.value,
                ]
            ),
        ),
    )
