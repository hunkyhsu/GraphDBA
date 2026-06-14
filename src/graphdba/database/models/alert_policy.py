import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from graphdba.database.base import Base


class AlertPolicyAction(StrEnum):
    FAST_PATH_SCRIPT = "fast_path_script"
    FAST_PATH_ESCALATE = "fast_path_escalate"
    SLOW_PATH_AGENT = "slow_path_agent"
    IGNORE = "ignore"


class AlertPolicyExecutionStatus(StrEnum):
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AlertPolicy(Base):
    __tablename__ = "alert_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    alert_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    action: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    handler_key: Mapped[str | None] = mapped_column(
        Text,
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    environment: Mapped[str | None] = mapped_column(
        Text,
    )
    cluster_name: Mapped[str | None] = mapped_column(
        Text,
    )
    database_name: Mapped[str | None] = mapped_column(
        Text,
    )
    instance: Mapped[str | None] = mapped_column(
        Text,
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default=text("100"),
    )
    cooldown_seconds: Mapped[int | None] = mapped_column(
        Integer,
    )
    max_executions_per_hour: Mapped[int | None] = mapped_column(
        Integer,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
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

    __table_args__ = (
        CheckConstraint(
            action.in_([action.value for action in AlertPolicyAction]),
            name="ck_alert_policies_action",
        ),
        CheckConstraint("priority >= 0", name="ck_alert_policies_priority"),
        CheckConstraint("cooldown_seconds IS NULL OR cooldown_seconds >= 0", name="ck_alert_policies_cooldown_seconds"),
        CheckConstraint(
            "max_executions_per_hour IS NULL OR max_executions_per_hour >= 0",
            name="ck_alert_policies_max_executions_per_hour",
        ),
        Index("idx_alert_policies_alert_name_enabled", "alert_name", "is_enabled"),
        Index(
            "idx_alert_policies_scope",
            "alert_name",
            "environment",
            "cluster_name",
            "database_name",
            "instance",
        ),
    )


class AlertPolicyExecution(Base):
    __tablename__ = "alert_policy_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alert_policies.id", ondelete="SET NULL"),
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    handler_key: Mapped[str | None] = mapped_column(
        Text,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=AlertPolicyExecutionStatus.STARTED.value,
        server_default=text("'STARTED'"),
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
    )
    execution_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    __table_args__ = (
        CheckConstraint(
            action.in_([action.value for action in AlertPolicyAction]),
            name="ck_alert_policy_executions_action",
        ),
        CheckConstraint(
            status.in_([status.value for status in AlertPolicyExecutionStatus]),
            name="ck_alert_policy_executions_status",
        ),
        Index("idx_alert_policy_executions_alert_id", "alert_id"),
        Index("idx_alert_policy_executions_policy_id", "policy_id"),
        Index("idx_alert_policy_executions_status_started_at", "status", "started_at"),
    )
