"""create alert policy registry tables

Revision ID: 2f4c1d8e9a10
Revises: 9b7c2e4f1a6d
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2f4c1d8e9a10"
down_revision: Union[str, Sequence[str], None] = "9b7c2e4f1a6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


alert_policies_table = sa.table(
    "alert_policies",
    sa.column("id", sa.UUID()),
    sa.column("alert_name", sa.Text()),
    sa.column("is_enabled", sa.Boolean()),
    sa.column("action", sa.Text()),
    sa.column("handler_key", sa.Text()),
    sa.column("requires_approval", sa.Boolean()),
    sa.column("environment", sa.Text()),
    sa.column("cluster_name", sa.Text()),
    sa.column("database_name", sa.Text()),
    sa.column("instance", sa.Text()),
    sa.column("priority", sa.Integer()),
    sa.column("cooldown_seconds", sa.Integer()),
    sa.column("max_executions_per_hour", sa.Integer()),
    sa.column("description", sa.Text()),
)


def _policy(
    alert_name: str,
    *,
    description: str,
    action: str = "slow_path_agent",
    handler_key: str | None = None,
    requires_approval: bool = True,
    priority: int = 100,
    cooldown_seconds: int | None = None,
    max_executions_per_hour: int | None = None,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "alert_name": alert_name,
        "is_enabled": True,
        "action": action,
        "handler_key": handler_key,
        "requires_approval": requires_approval,
        "environment": None,
        "cluster_name": None,
        "database_name": None,
        "instance": None,
        "priority": priority,
        "cooldown_seconds": cooldown_seconds,
        "max_executions_per_hour": max_executions_per_hour,
        "description": description,
    }


def upgrade() -> None:
    op.create_table(
        "alert_policies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("alert_name", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("handler_key", sa.Text(), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("environment", sa.Text(), nullable=True),
        sa.Column("cluster_name", sa.Text(), nullable=True),
        sa.Column("database_name", sa.Text(), nullable=True),
        sa.Column("instance", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=True),
        sa.Column("max_executions_per_hour", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "action IN ('fast_path_script', 'fast_path_escalate', 'slow_path_agent', 'ignore')",
            name="ck_alert_policies_action",
        ),
        sa.CheckConstraint("priority >= 0", name="ck_alert_policies_priority"),
        sa.CheckConstraint("cooldown_seconds IS NULL OR cooldown_seconds >= 0", name="ck_alert_policies_cooldown_seconds"),
        sa.CheckConstraint(
            "max_executions_per_hour IS NULL OR max_executions_per_hour >= 0",
            name="ck_alert_policies_max_executions_per_hour",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_alert_policies_alert_name_enabled", "alert_policies", ["alert_name", "is_enabled"])
    op.create_index(
        "idx_alert_policies_scope",
        "alert_policies",
        ["alert_name", "environment", "cluster_name", "database_name", "instance"],
    )

    op.create_table(
        "alert_policy_executions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("policy_id", sa.UUID(), nullable=True),
        sa.Column("alert_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("handler_key", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'STARTED'"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("execution_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "action IN ('fast_path_script', 'fast_path_escalate', 'slow_path_agent', 'ignore')",
            name="ck_alert_policy_executions_action",
        ),
        sa.CheckConstraint(
            "status IN ('STARTED', 'SUCCESS', 'FAILED', 'SKIPPED')",
            name="ck_alert_policy_executions_status",
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["alert_policies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_alert_policy_executions_alert_id", "alert_policy_executions", ["alert_id"])
    op.create_index("idx_alert_policy_executions_policy_id", "alert_policy_executions", ["policy_id"])
    op.create_index(
        "idx_alert_policy_executions_status_started_at",
        "alert_policy_executions",
        ["status", "started_at"],
    )

    op.bulk_insert(
        alert_policies_table,
        [
            _policy(
                "PostgreSQLInstanceDown",
                action="fast_path_escalate",
                priority=10,
                description="Escalate database availability incidents to human DBA/platform review.",
            ),
            _policy(
                "PostgreSQLConnectionsExhausted",
                action="fast_path_script",
                handler_key="postgres_connections_exhausted_fast_path",
                requires_approval=False,
                priority=20,
                cooldown_seconds=300,
                max_executions_per_hour=6,
                description="Fast-path policy for exhausted PostgreSQL connections.",
            ),
            _policy(
                "PostgreSQLConnectionsHigh",
                description="Run GraphDBA diagnosis for high connection pressure.",
            ),
            _policy(
                "PostgreSQLDeadlocksDetected",
                description="Run GraphDBA diagnosis for detected PostgreSQL deadlocks.",
            ),
            _policy(
                "PostgreSQLRollbackRateHigh",
                description="Run GraphDBA diagnosis for high rollback rate.",
            ),
            _policy(
                "PostgreSQLTableNotAutovacuumed",
                description="Run GraphDBA diagnosis for tables missing autovacuum.",
            ),
            _policy(
                "PostgreSQLTableNotAutoanalyzed",
                description="Run GraphDBA diagnosis for tables missing autoanalyze.",
            ),
            _policy(
                "PostgreSQLDeadTuplesHigh",
                description="Run GraphDBA diagnosis for high dead tuple ratio.",
            ),
            _policy(
                "PostgreSQLLocksHigh",
                description="Run GraphDBA diagnosis for elevated lock pressure.",
            ),
            _policy(
                "PostgreSQLReplicationLagHigh",
                description="Run GraphDBA diagnosis for PostgreSQL replication lag.",
            ),
        ],
    )


def downgrade() -> None:
    op.drop_index("idx_alert_policy_executions_status_started_at", table_name="alert_policy_executions")
    op.drop_index("idx_alert_policy_executions_policy_id", table_name="alert_policy_executions")
    op.drop_index("idx_alert_policy_executions_alert_id", table_name="alert_policy_executions")
    op.drop_table("alert_policy_executions")
    op.drop_index("idx_alert_policies_scope", table_name="alert_policies")
    op.drop_index("idx_alert_policies_alert_name_enabled", table_name="alert_policies")
    op.drop_table("alert_policies")
