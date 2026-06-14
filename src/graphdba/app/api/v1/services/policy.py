import logging
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.app.api.v1.services.fast_path_scripts import run_fast_path_script
from graphdba.database.models.alert import Alert, AlertStatus
from graphdba.database.models.alert_policy import (
    AlertPolicy,
    AlertPolicyAction,
    AlertPolicyExecutionStatus,
)
from graphdba.database.repositories import alert_policies, alerts

logger = logging.getLogger(__name__)


class AlertPolicyResult(BaseModel):
    action: AlertPolicyAction
    policy_id: str | None = None
    handler_key: str | None = None


async def _record_policy_success(
    session: AsyncSession,
    *,
    alert: Alert,
    action: AlertPolicyAction,
    policy: AlertPolicy | None = None,
    metadata: dict | None = None,
) -> None:
    await alert_policies.create_policy_execution(
        session,
        alert_id=alert.id,
        policy_id=policy.id if policy else None,
        action=action.value,
        handler_key=policy.handler_key if policy else None,
        status=AlertPolicyExecutionStatus.SUCCESS.value,
        execution_metadata=metadata,
    )


async def _skip_fast_path_script(
    session: AsyncSession,
    *,
    alert: Alert,
    policy: AlertPolicy,
    reason: str,
) -> AlertPolicyResult:
    logger.info("Fast-path script skipped for alert %s: %s", alert.name, reason)
    await alerts.update_alert_status(
        session,
        alert.id,
        status=AlertStatus.ESCALATED.value,
        escalation_reason=reason,
        clear_failure_reason=True,
    )
    await alert_policies.create_policy_execution(
        session,
        alert_id=alert.id,
        policy_id=policy.id,
        action=AlertPolicyAction.FAST_PATH_SCRIPT.value,
        handler_key=policy.handler_key,
        status=AlertPolicyExecutionStatus.SKIPPED.value,
        execution_metadata={
            "reason": reason,
            "requires_approval": policy.requires_approval,
        },
    )
    return AlertPolicyResult(
        action=AlertPolicyAction.FAST_PATH_ESCALATE,
        policy_id=str(policy.id),
        handler_key=policy.handler_key,
    )


async def _enforce_fast_path_limits(
    session: AsyncSession,
    *,
    alert: Alert,
    policy: AlertPolicy,
) -> AlertPolicyResult | None:
    now = datetime.now(timezone.utc)
    if policy.cooldown_seconds:
        latest_success = await alert_policies.get_latest_policy_execution(
            session,
            policy_id=policy.id,
            status=AlertPolicyExecutionStatus.SUCCESS.value,
        )
        if latest_success is not None:
            cooldown_until = latest_success.started_at + timedelta(seconds=policy.cooldown_seconds)
            if cooldown_until > now:
                return await _skip_fast_path_script(
                    session,
                    alert=alert,
                    policy=policy,
                    reason=f"Fast-path policy {policy.id} is in cooldown until {cooldown_until.isoformat()}",
                )

    if policy.max_executions_per_hour is not None:
        executions_last_hour = await alert_policies.count_policy_executions_since(
            session,
            policy_id=policy.id,
            since=now - timedelta(hours=1),
            status=AlertPolicyExecutionStatus.SUCCESS.value,
        )
        if executions_last_hour >= policy.max_executions_per_hour:
            return await _skip_fast_path_script(
                session,
                alert=alert,
                policy=policy,
                reason=f"Fast-path policy {policy.id} reached max executions per hour",
            )

    return None


async def apply_alert_policy(
    session: AsyncSession,
    *,
    alert: Alert,
) -> AlertPolicyResult:
    alert_name = alert.name
    policy = await alert_policies.find_matching_policy(session, alert)

    if policy is None:
        reason = (
            f"No enabled alert policy found for {alert_name}; "
            "manual DBA review required"
        )
        logger.warning("No enabled alert policy found for alert %s", alert_name)
        await alerts.update_alert_status(
            session,
            alert.id,
            status=AlertStatus.ESCALATED.value,
            escalation_reason=reason,
            clear_failure_reason=True,
        )
        await _record_policy_success(
            session,
            alert=alert,
            action=AlertPolicyAction.FAST_PATH_ESCALATE,
            metadata={"reason": "policy_not_found"},
        )
        return AlertPolicyResult(action=AlertPolicyAction.FAST_PATH_ESCALATE)

    action = AlertPolicyAction(policy.action)
    if action == AlertPolicyAction.FAST_PATH_SCRIPT:
        logger.info("Fast path policy triggered for alert %s by policy %s", alert_name, policy.id)
        limit_result = await _enforce_fast_path_limits(
            session,
            alert=alert,
            policy=policy,
        )
        if limit_result is not None:
            return limit_result

        execution = await alert_policies.create_policy_execution(
            session,
            alert_id=alert.id,
            policy_id=policy.id,
            action=action.value,
            handler_key=policy.handler_key,
            execution_metadata={"requires_approval": policy.requires_approval},
        )
        try:
            script_result = await run_fast_path_script(
                session,
                handler_key=policy.handler_key,
                alert=alert,
            )
        except Exception as exc:
            reason = f"Fast-path script failed for {alert_name}: {exc}"
            logger.warning(reason, exc_info=True)
            await alerts.update_alert_status(
                session,
                alert.id,
                status=AlertStatus.ESCALATED.value,
                escalation_reason=reason,
                clear_failure_reason=True,
            )
            await alert_policies.finish_policy_execution(
                session,
                execution,
                status=AlertPolicyExecutionStatus.FAILED.value,
                error_message=str(exc),
                execution_metadata={"requires_approval": policy.requires_approval},
            )
            return AlertPolicyResult(
                action=AlertPolicyAction.FAST_PATH_ESCALATE,
                policy_id=str(policy.id),
                handler_key=policy.handler_key,
            )

        if script_result.solved:
            await alerts.update_alert_status(
                session,
                alert.id,
                status=AlertStatus.SOLVED.value,
                solved_at=datetime.now(timezone.utc),
                clear_failure_reason=True,
            )
            execution_status = AlertPolicyExecutionStatus.SUCCESS.value
            result_action = action
        else:
            reason = f"Fast-path script completed but did not resolve {alert_name}; manual DBA review required"
            await alerts.update_alert_status(
                session,
                alert.id,
                status=AlertStatus.ESCALATED.value,
                escalation_reason=reason,
                clear_failure_reason=True,
            )
            execution_status = AlertPolicyExecutionStatus.SKIPPED.value
            result_action = AlertPolicyAction.FAST_PATH_ESCALATE

        await alert_policies.finish_policy_execution(
            session,
            execution,
            status=execution_status,
            execution_metadata={
                "requires_approval": policy.requires_approval,
                **script_result.metadata,
            },
        )
        return AlertPolicyResult(
            action=result_action,
            policy_id=str(policy.id),
            handler_key=policy.handler_key,
        )

    if action == AlertPolicyAction.FAST_PATH_ESCALATE:
        reason = f"Alert policy {policy.id} escalated {alert_name}; manual DBA review required"
        logger.info("Escalation policy triggered for alert %s by policy %s", alert_name, policy.id)
        await alerts.update_alert_status(
            session,
            alert.id,
            status=AlertStatus.ESCALATED.value,
            escalation_reason=reason,
            clear_failure_reason=True,
        )
        await _record_policy_success(
            session,
            alert=alert,
            action=action,
            policy=policy,
            metadata={"requires_approval": policy.requires_approval},
        )
        return AlertPolicyResult(
            action=action,
            policy_id=str(policy.id),
            handler_key=policy.handler_key,
        )

    if action == AlertPolicyAction.IGNORE:
        logger.info("Ignore policy triggered for alert %s by policy %s", alert_name, policy.id)
        await alerts.update_alert_status(
            session,
            alert.id,
            status=AlertStatus.RESOLVED.value,
            resolved_at=datetime.now(timezone.utc),
            clear_failure_reason=True,
        )
        await _record_policy_success(
            session,
            alert=alert,
            action=action,
            policy=policy,
            metadata={"requires_approval": policy.requires_approval},
        )
        return AlertPolicyResult(
            action=action,
            policy_id=str(policy.id),
            handler_key=policy.handler_key,
        )

    await alerts.update_alert_status(
        session,
        alert.id,
        status=AlertStatus.RUNNING.value,
        clear_failure_reason=True,
    )
    await _record_policy_success(
        session,
        alert=alert,
        action=AlertPolicyAction.SLOW_PATH_AGENT,
        policy=policy,
        metadata={"requires_approval": policy.requires_approval},
    )
    return AlertPolicyResult(
        action=AlertPolicyAction.SLOW_PATH_AGENT,
        policy_id=str(policy.id),
        handler_key=policy.handler_key,
    )
