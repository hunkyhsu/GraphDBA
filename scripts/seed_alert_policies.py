import asyncio
from dataclasses import dataclass

from graphdba.database.models.alert_policy import AlertPolicyAction
from graphdba.database.repositories import alert_policies
from graphdba.database.session import AsyncSessionLocal, engine


@dataclass(frozen=True)
class SeedAlertPolicy:
    alert_name: str
    action: str
    description: str
    handler_key: str | None = None
    requires_approval: bool = True
    priority: int = 100
    cooldown_seconds: int | None = None
    max_executions_per_hour: int | None = None
    is_enabled: bool = True


SEED_ALERT_POLICIES = [
    SeedAlertPolicy(
        alert_name="PostgreSQLInstanceDown",
        action=AlertPolicyAction.FAST_PATH_ESCALATE.value,
        description="Escalate PostgreSQL availability incidents to human DBA/platform review.",
        priority=10,
    ),
    SeedAlertPolicy(
        alert_name="PostgreSQLConnectionsHigh",
        action=AlertPolicyAction.SLOW_PATH_AGENT.value,
        description="Run GraphDBA diagnosis for high PostgreSQL connection usage.",
    ),
    SeedAlertPolicy(
        alert_name="PostgreSQLConnectionsExhausted",
        action=AlertPolicyAction.FAST_PATH_SCRIPT.value,
        handler_key="postgres_connections_exhausted_fast_path",
        requires_approval=False,
        priority=20,
        cooldown_seconds=300,
        max_executions_per_hour=6,
        description="Run the approved fast-path handler for nearly exhausted PostgreSQL connections.",
    ),
    SeedAlertPolicy(
        alert_name="PostgreSQLDeadlocksDetected",
        action=AlertPolicyAction.SLOW_PATH_AGENT.value,
        description="Run GraphDBA diagnosis for detected PostgreSQL deadlocks.",
    ),
    SeedAlertPolicy(
        alert_name="PostgreSQLRollbackRateHigh",
        action=AlertPolicyAction.SLOW_PATH_AGENT.value,
        description="Run GraphDBA diagnosis for high PostgreSQL rollback rate.",
    ),
    SeedAlertPolicy(
        alert_name="PostgreSQLTableNotAutovacuumed",
        action=AlertPolicyAction.SLOW_PATH_AGENT.value,
        description="Run GraphDBA diagnosis for tables missing autovacuum.",
    ),
    SeedAlertPolicy(
        alert_name="PostgreSQLTableNotAutoanalyzed",
        action=AlertPolicyAction.SLOW_PATH_AGENT.value,
        description="Run GraphDBA diagnosis for tables missing autoanalyze.",
    ),
    SeedAlertPolicy(
        alert_name="PostgreSQLDeadTuplesHigh",
        action=AlertPolicyAction.SLOW_PATH_AGENT.value,
        description="Run GraphDBA diagnosis for high PostgreSQL dead tuple pressure.",
    ),
    SeedAlertPolicy(
        alert_name="PostgreSQLLocksHigh",
        action=AlertPolicyAction.SLOW_PATH_AGENT.value,
        description="Run GraphDBA diagnosis for elevated PostgreSQL lock usage.",
    ),
    SeedAlertPolicy(
        alert_name="PostgreSQLReplicationLagHigh",
        action=AlertPolicyAction.SLOW_PATH_AGENT.value,
        description="Run GraphDBA diagnosis for PostgreSQL replication lag.",
    ),
]


async def seed_alert_policies() -> None:
    async with AsyncSessionLocal() as session:
        for seed_policy in SEED_ALERT_POLICIES:
            await alert_policies.upsert_global_policy(
                session,
                alert_name=seed_policy.alert_name,
                is_enabled=seed_policy.is_enabled,
                action=seed_policy.action,
                handler_key=seed_policy.handler_key,
                requires_approval=seed_policy.requires_approval,
                priority=seed_policy.priority,
                cooldown_seconds=seed_policy.cooldown_seconds,
                max_executions_per_hour=seed_policy.max_executions_per_hour,
                description=seed_policy.description,
            )

        await session.commit()


async def main() -> None:
    try:
        await seed_alert_policies()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
