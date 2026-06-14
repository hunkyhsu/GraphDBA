from __future__ import annotations

import asyncio
import logging
import os
import socket
from uuid import uuid4

from langgraph.graph.state import CompiledStateGraph

from graphdba.agents.state import AgentWorkflowStatus, FinalPlan
from graphdba.app.api.v1.services.policy import AlertPolicyAction, apply_alert_policy
from graphdba.database.models.alert import Alert, AlertStatus
from graphdba.database.repositories import alerts, run_leases, tickets
from graphdba.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

RECOVERY_OWNER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


def build_agent_state(
    *,
    alert_payload: dict,
    failure_reason: str | None = None,
) -> dict:
    return {
        "alert": alert_payload,
        "current_hypotheses": [],
        "rejected_hypotheses": [],
        "final_plan": None,
        "attempt_count": 0,
        "failure_reason": failure_reason,
    }


def build_alert_payload_from_record(alert: Alert) -> dict:
    return {
        "id": str(alert.id),
        "alertname": alert.name,
        "instance": alert.instance or "",
        "severity": alert.severity,
        "summary": alert.summary,
        "description": alert.description or "",
        "raw_payload": alert.raw_payload,
    }


async def propose_ticket_if_planned(graph: CompiledStateGraph, config: dict) -> None:
    state = graph.get_state(config=config)
    if state.values.get("workflow_status") != AgentWorkflowStatus.PLANNED.value:
        return

    try:
        plan = FinalPlan.model_validate(state.values["final_plan"])
        async with AsyncSessionLocal() as session:
            existing_ticket = await tickets.get_pending_ticket_by_alert_id(session, plan.target_alert_id)
            if existing_ticket is not None:
                logger.info(
                    "Pending change ticket %s already exists for alert %s",
                    existing_ticket.id,
                    plan.target_alert_id,
                )
                await alerts.update_alert_status(
                    session,
                    plan.target_alert_id,
                    status=AlertStatus.WAITING_APPROVAL.value,
                    clear_failure_reason=True,
                )
                await session.commit()
                return
            ticket = await tickets.create_ticket_from_plan(
                session,
                alert_id=plan.target_alert_id,
                target_hypothesis_id=plan.target_hypothesis_id,
                proposed_steps=[step.model_dump(mode="json") for step in plan.execution_steps],
                change_reason=plan.change_reason,
                rollback_sql=plan.rollback_sql,
                rollback_note=plan.rollback_note,
                risk_level=plan.risk_level.value,
            )
            await alerts.update_alert_status(
                session,
                plan.target_alert_id,
                status=AlertStatus.WAITING_APPROVAL.value,
                clear_failure_reason=True,
            )
            await session.commit()
    except Exception as exc:
        logger.exception("Failed to create change ticket for thread %s", config["configurable"]["thread_id"])
        graph.update_state(config, {
            "workflow_status": AgentWorkflowStatus.FAILED.value,
            "failure_reason": f"Failed to create change ticket: {exc}",
        })
        try:
            alert_id = state.values.get("alert", {}).get("id")
            if alert_id:
                async with AsyncSessionLocal() as session:
                    await alerts.update_alert_status(
                        session,
                        alert_id,
                        status=AlertStatus.FAILED.value,
                        failure_reason=f"Failed to create change ticket: {exc}",
                    )
                    await session.commit()
        except Exception:
            logger.exception("Failed to persist alert failure after ticket proposal error")
        return

    logger.info("Created change ticket %s for thread %s", ticket.id, config["configurable"]["thread_id"])


async def sync_terminal_graph_state(graph: CompiledStateGraph, alert_id: str, config: dict) -> None:
    state = graph.get_state(config=config)
    workflow_status = state.values.get("workflow_status")
    failure_reason = state.values.get("failure_reason")
    if workflow_status not in (AgentWorkflowStatus.FAILED.value, AgentWorkflowStatus.ESCALATED.value):
        return

    async with AsyncSessionLocal() as session:
        await alerts.update_alert_status(
            session,
            alert_id,
            status=AlertStatus.ESCALATED.value if workflow_status == AgentWorkflowStatus.ESCALATED.value else AlertStatus.FAILED.value,
            failure_reason=failure_reason if workflow_status == AgentWorkflowStatus.FAILED.value else None,
            escalation_reason=failure_reason if workflow_status == AgentWorkflowStatus.ESCALATED.value else None,
        )
        await session.commit()


async def run_graph_with_lease(
    *,
    graph: CompiledStateGraph,
    alert_id: str,
    config: dict,
    initial_state: dict | None,
    owner_id: str = RECOVERY_OWNER_ID,
) -> None:
    async with AsyncSessionLocal() as session:
        acquired = await run_leases.acquire_run_lease(
            session,
            alert_id=alert_id,
            thread_id=config["configurable"]["thread_id"],
            owner_id=owner_id,
        )
        await session.commit()
    if not acquired:
        logger.info("Run lease already active for alert %s", alert_id)
        return

    try:
        async for _ in graph.astream(initial_state, config):
            async with AsyncSessionLocal() as session:
                await run_leases.heartbeat_run_lease(session, alert_id=alert_id, owner_id=owner_id)
                await session.commit()
        await propose_ticket_if_planned(graph, config)
        await sync_terminal_graph_state(graph, alert_id, config)
    except Exception as exc:
        logger.exception("Graph run failed for alert %s", alert_id)
        async with AsyncSessionLocal() as session:
            await alerts.update_alert_status(
                session,
                alert_id,
                status=AlertStatus.FAILED.value,
                failure_reason=f"Graph run failed: {exc}",
            )
            await session.commit()
    finally:
        async with AsyncSessionLocal() as session:
            await run_leases.release_run_lease(session, alert_id=alert_id, owner_id=owner_id)
            await session.commit()


async def propose_ticket_with_lease(
    *,
    graph: CompiledStateGraph,
    alert_id: str,
    config: dict,
    owner_id: str = RECOVERY_OWNER_ID,
) -> None:
    async with AsyncSessionLocal() as session:
        acquired = await run_leases.acquire_run_lease(
            session,
            alert_id=alert_id,
            thread_id=config["configurable"]["thread_id"],
            owner_id=owner_id,
        )
        await session.commit()
    if not acquired:
        logger.info("Run lease already active for planned alert %s", alert_id)
        return

    try:
        await propose_ticket_if_planned(graph, config)
    finally:
        async with AsyncSessionLocal() as session:
            await run_leases.release_run_lease(session, alert_id=alert_id, owner_id=owner_id)
            await session.commit()


async def recover_alert_from_record(graph: CompiledStateGraph, alert: Alert) -> None:
    alert_id = str(alert.id)
    config = {"configurable": {"thread_id": alert_id}}
    state = graph.get_state(config=config)

    async with AsyncSessionLocal() as session:
        active_lease = await run_leases.get_active_lease_by_alert_id(session, alert.id)
    if active_lease is not None:
        logger.info("Active run lease exists for alert %s; recovery skipped", alert_id)
        return

    if state.values:
        workflow_status = state.values.get("workflow_status")
        if workflow_status == AgentWorkflowStatus.PLANNED.value:
            await propose_ticket_with_lease(graph=graph, alert_id=alert_id, config=config)
            return
        if state.next:
            await run_graph_with_lease(graph=graph, alert_id=alert_id, config=config, initial_state=None)
            return
        if workflow_status in (AgentWorkflowStatus.FAILED.value, AgentWorkflowStatus.ESCALATED.value):
            await sync_terminal_graph_state(graph, alert_id, config)
            return
        logger.info("No recovery action for alert %s with workflow status %s", alert_id, workflow_status)
        return

    if alert.status == AlertStatus.RECEIVED.value:
        async with AsyncSessionLocal() as session:
            attached_alert = await alerts.get_alert_by_id(session, alert.id)
            if attached_alert is None:
                return
            policy_result = await apply_alert_policy(session, alert=attached_alert)
            await session.commit()
        if policy_result.action == AlertPolicyAction.SLOW_PATH_AGENT:
            await run_graph_with_lease(
                graph=graph,
                alert_id=alert_id,
                config=config,
                initial_state=build_agent_state(alert_payload=build_alert_payload_from_record(alert)),
            )
        return

    if alert.status == AlertStatus.RUNNING.value:
        await run_graph_with_lease(
            graph=graph,
            alert_id=alert_id,
            config=config,
            initial_state=build_agent_state(alert_payload=build_alert_payload_from_record(alert)),
        )
        return

    if alert.status == AlertStatus.WAITING_APPROVAL.value:
        logger.info("Alert %s is waiting approval; graph recovery skipped", alert_id)
        return


async def recover_active_alerts(graph: CompiledStateGraph) -> None:
    async with AsyncSessionLocal() as session:
        recoverable_alerts = await alerts.list_recoverable_alerts(session)
    logger.info("Recovering %d active alerts", len(recoverable_alerts))
    results = await asyncio.gather(
        *(recover_alert_from_record(graph, alert) for alert in recoverable_alerts),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, Exception):
            logger.error(
                "Active alert recovery failed",
                exc_info=(type(result), result, result.__traceback__),
            )
