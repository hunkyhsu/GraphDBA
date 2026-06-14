from datetime import datetime, timezone
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.database.models.alert import Alert
from graphdba.database.models.alert_policy import (
    AlertPolicy,
    AlertPolicyExecution,
    AlertPolicyExecutionStatus,
)


def _scope_matches(policy_value: str | None, alert_value: str | None) -> bool:
    return policy_value in (None, "*") or policy_value == alert_value


def _scope_specificity(policy: AlertPolicy) -> int:
    return sum(
        value not in (None, "*")
        for value in (
            policy.environment,
            policy.cluster_name,
            policy.database_name,
            policy.instance,
        )
    )


async def find_matching_policy(session: AsyncSession, alert: Alert) -> AlertPolicy | None:
    stmt = (
        select(AlertPolicy)
        .where(AlertPolicy.alert_name == alert.name)
        .where(AlertPolicy.is_enabled.is_(True))
        .where(or_(AlertPolicy.environment.is_(None), AlertPolicy.environment == "*", AlertPolicy.environment == alert.environment))
        .where(or_(AlertPolicy.cluster_name.is_(None), AlertPolicy.cluster_name == "*", AlertPolicy.cluster_name == alert.cluster_name))
        .where(
            or_(
                AlertPolicy.database_name.is_(None),
                AlertPolicy.database_name == "*",
                AlertPolicy.database_name == alert.database_name,
            )
        )
        .where(or_(AlertPolicy.instance.is_(None), AlertPolicy.instance == "*", AlertPolicy.instance == alert.instance))
        .order_by(AlertPolicy.priority.asc(), AlertPolicy.updated_at.desc(), AlertPolicy.id.asc())
    )
    result = await session.execute(stmt)
    policies = list(result.scalars().all())
    if not policies:
        return None

    matching_policies = [
        policy
        for policy in policies
        if _scope_matches(policy.environment, alert.environment)
        and _scope_matches(policy.cluster_name, alert.cluster_name)
        and _scope_matches(policy.database_name, alert.database_name)
        and _scope_matches(policy.instance, alert.instance)
    ]
    if not matching_policies:
        return None

    return sorted(
        matching_policies,
        key=lambda policy: (
            policy.priority,
            -_scope_specificity(policy),
            -policy.updated_at.timestamp(),
            str(policy.id),
        ),
    )[0]


async def get_global_policy_by_alert_name(
    session: AsyncSession,
    alert_name: str,
) -> AlertPolicy | None:
    stmt = (
        select(AlertPolicy)
        .where(AlertPolicy.alert_name == alert_name)
        .where(AlertPolicy.environment.is_(None))
        .where(AlertPolicy.cluster_name.is_(None))
        .where(AlertPolicy.database_name.is_(None))
        .where(AlertPolicy.instance.is_(None))
        .order_by(AlertPolicy.priority.asc(), AlertPolicy.updated_at.desc(), AlertPolicy.id.asc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_global_policy(
    session: AsyncSession,
    *,
    alert_name: str,
    is_enabled: bool,
    action: str,
    handler_key: str | None = None,
    requires_approval: bool = True,
    priority: int = 100,
    cooldown_seconds: int | None = None,
    max_executions_per_hour: int | None = None,
    description: str | None = None,
) -> AlertPolicy:
    policy = await get_global_policy_by_alert_name(session, alert_name)
    if policy is None:
        policy = AlertPolicy(
            alert_name=alert_name,
            is_enabled=is_enabled,
            action=action,
            handler_key=handler_key,
            requires_approval=requires_approval,
            priority=priority,
            cooldown_seconds=cooldown_seconds,
            max_executions_per_hour=max_executions_per_hour,
            description=description,
        )
        session.add(policy)
    else:
        policy.is_enabled = is_enabled
        policy.action = action
        policy.handler_key = handler_key
        policy.requires_approval = requires_approval
        policy.priority = priority
        policy.cooldown_seconds = cooldown_seconds
        policy.max_executions_per_hour = max_executions_per_hour
        policy.description = description

    await session.flush()
    return policy


async def create_policy_execution(
    session: AsyncSession,
    *,
    alert_id: UUIDType | str,
    action: str,
    policy_id: UUIDType | str | None = None,
    handler_key: str | None = None,
    status: str = AlertPolicyExecutionStatus.STARTED.value,
    error_message: str | None = None,
    execution_metadata: dict[str, Any] | None = None,
) -> AlertPolicyExecution:
    execution = AlertPolicyExecution(
        policy_id=UUIDType(str(policy_id)) if policy_id is not None else None,
        alert_id=UUIDType(str(alert_id)),
        action=action,
        handler_key=handler_key,
        status=status,
        error_message=error_message,
        execution_metadata=execution_metadata or {},
    )
    if status != AlertPolicyExecutionStatus.STARTED.value:
        execution.finished_at = datetime.now(timezone.utc)
    session.add(execution)
    await session.flush()
    return execution


async def get_latest_policy_execution(
    session: AsyncSession,
    *,
    policy_id: UUIDType | str,
    status: str | None = None,
) -> AlertPolicyExecution | None:
    stmt = (
        select(AlertPolicyExecution)
        .where(AlertPolicyExecution.policy_id == UUIDType(str(policy_id)))
        .order_by(AlertPolicyExecution.started_at.desc(), AlertPolicyExecution.id.desc())
        .limit(1)
    )
    if status is not None:
        stmt = stmt.where(AlertPolicyExecution.status == status)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def count_policy_executions_since(
    session: AsyncSession,
    *,
    policy_id: UUIDType | str,
    since: datetime,
    status: str | None = None,
) -> int:
    stmt = (
        select(func.count())
        .select_from(AlertPolicyExecution)
        .where(AlertPolicyExecution.policy_id == UUIDType(str(policy_id)))
        .where(AlertPolicyExecution.started_at >= since)
    )
    if status is not None:
        stmt = stmt.where(AlertPolicyExecution.status == status)
    result = await session.execute(stmt)
    return result.scalar_one()


async def finish_policy_execution(
    session: AsyncSession,
    execution: AlertPolicyExecution,
    *,
    status: str,
    error_message: str | None = None,
    execution_metadata: dict[str, Any] | None = None,
) -> AlertPolicyExecution:
    execution.status = status
    execution.error_message = error_message
    if execution_metadata is not None:
        execution.execution_metadata = execution_metadata
    execution.finished_at = datetime.now(timezone.utc)
    await session.flush()
    return execution
