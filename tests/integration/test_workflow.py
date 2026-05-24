from __future__ import annotations
import asyncio
import logging
import pytest
from uuid import uuid4
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

from graphdba.agents.graph import build_graph
from graphdba.agents.state import ApprovalDecision, FinalPlan, NodeName, WorkflowStatus
from graphdba.config.dependencies import get_reasoning_llm, get_chat_llm
from tests.conftest import ManagedMockClient

if TYPE_CHECKING:
    from graphdba.agents.state import AgentStateUpdate

logger = logging.getLogger(__name__)

FIXTURE_PATH = "tests/data/deadlock_sample.yaml"


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_config() -> dict:
    return {"configurable": {"thread_id": f"test_{uuid4().hex[:8]}"}}


def _make_initial_state(alert: dict) -> AgentStateUpdate:
    return {
        "alert": alert,
        "workflow_status": WorkflowStatus.PENDING.value,
        "attempt_count": 0,
        "current_hypotheses": [],
        "rejected_hypotheses": [],
    }


async def _stream_graph(graph, initial_state: dict | None, config: dict) -> None:
    async for event in graph.astream(initial_state, config):
        for node_name, state_update in event.items():
            logger.debug("node=%s status=%s", node_name, state_update.get("workflow_status", "—"))


# ── unit: triage node (no LLM / MCP required) ────────────────────────────────

def test_triage_physical_error_is_bypassed():
    """Critical physical errors must short-circuit to FAILED without LLM calls."""
    from graphdba.agents.triage import triage_node

    state: AgentStateUpdate = {
        "alert": {
            "fingerprint": "phys_001",
            "alertname": "Disk Corruption",
            "instance": "127.0.0.1:5432",
            "severity": "critical",
            "status": "firing",
            "summary": "Disk corruption detected",
            "description": "bad block found on data volume",
            "startsAt": "2026-05-11T10:00:00Z",
            "raw_payload": {},
        },
        "workflow_status": WorkflowStatus.PENDING.value,
        "current_hypotheses": [], "rejected_hypotheses": [],
        "attempt_count": 0, "final_plan": None,
        "approval_decision": None, "human_feedback": None, "failed_reason": None,
    }
    result = triage_node(state)
    assert result["workflow_status"] == WorkflowStatus.FAILED


def test_triage_normal_alert_initialises_state():
    """Normal alert must set TRIAGED and zero-out all mutable state fields."""
    from graphdba.agents.triage import triage_node

    state: AgentStateUpdate = {
        "alert": {
            "fingerprint": "norm_001",
            "alertname": "PostgreSQL Deadlock Detected",
            "instance": "127.0.0.1:5432",
            "severity": "high",
            "status": "firing",
            "summary": "Deadlock detected",
            "description": "Postgres log: ERROR: deadlock detected.",
            "startsAt": "2026-05-11T10:00:00Z",
            "raw_payload": {},
        },
        "workflow_status": WorkflowStatus.PENDING.value,
        "current_hypotheses": [], "rejected_hypotheses": [],
        "attempt_count": 0, "final_plan": None,
        "approval_decision": None, "human_feedback": None, "failed_reason": None,
    }
    result = triage_node(state)
    assert result["workflow_status"] == WorkflowStatus.TRIAGED.value
    assert result["attempt_count"] == 0
    assert result["final_plan"] is None
    assert result["approval_decision"] is None
    assert result["failed_reason"] is None


# ── integration: full workflow (requires LLM API credentials in .env) ─────────

def test_full_workflow_reaches_planning_interrupt():
    """Graph must pause at execution_node with a valid FinalPlan after planning."""
    asyncio.run(_full_workflow_reaches_planning_interrupt())


async def _full_workflow_reaches_planning_interrupt():
    llm_reasoning = get_reasoning_llm()
    llm_chat = get_chat_llm()
    alert = ManagedMockClient.load_alert_payload(FIXTURE_PATH)

    async with AsyncExitStack() as stack:
        mcp_read = await stack.enter_async_context(ManagedMockClient(FIXTURE_PATH, "read"))
        mcp_write = await stack.enter_async_context(ManagedMockClient(FIXTURE_PATH, "write"))
        graph = build_graph(llm_reasoning, llm_chat, mcp_read, mcp_write)
        config = _make_config()

        await _stream_graph(graph, _make_initial_state(alert), config)

        snapshot = graph.get_state(config)
        assert NodeName.EXECUTION in snapshot.next, (
            f"Graph should pause before execution_node; next={snapshot.next}, "
            f"status={snapshot.values.get('workflow_status')}"
        )
        status = snapshot.values.get("workflow_status")
        assert status == WorkflowStatus.PLANNED.value, f"Expected PLANNED, got {status}"

        raw_plan = snapshot.values.get("final_plan")
        assert raw_plan is not None, "final_plan must be populated before the interrupt"
        plan = FinalPlan.model_validate(raw_plan)
        assert plan.execution_steps, "final_plan must contain at least one execution step"
        assert plan.target_alert_id == "alert_deadlock_001"


def test_full_workflow_with_approval():
    """After human approval the execution node must run and reach a terminal status."""
    asyncio.run(_full_workflow_with_approval())


async def _full_workflow_with_approval():
    llm_reasoning = get_reasoning_llm()
    llm_chat = get_chat_llm()
    alert = ManagedMockClient.load_alert_payload(FIXTURE_PATH)

    async with AsyncExitStack() as stack:
        mcp_read = await stack.enter_async_context(ManagedMockClient(FIXTURE_PATH, "read"))
        mcp_write = await stack.enter_async_context(ManagedMockClient(FIXTURE_PATH, "write"))
        graph = build_graph(llm_reasoning, llm_chat, mcp_read, mcp_write)
        config = _make_config()

        await _stream_graph(graph, _make_initial_state(alert), config)

        snapshot = graph.get_state(config)
        if NodeName.EXECUTION not in snapshot.next:
            pytest.skip(
                f"Workflow did not reach planning stage "
                f"(status={snapshot.values.get('workflow_status')}); skipping."
            )

        graph.update_state(config, {
            "approval_decision": ApprovalDecision.APPROVED,
            "human_feedback": "Approved by automated test.",
        })
        await _stream_graph(graph, None, config)

        final = graph.get_state(config)
        final_status = final.values.get("workflow_status")
        assert final_status in (WorkflowStatus.COMPLETED.value, WorkflowStatus.FAILED.value), (
            f"Unexpected terminal status after approval: {final_status}"
        )
        logger.info("approval path finished with status=%s", final_status)


def test_full_workflow_with_rejection():
    """Human rejection must terminate with COMPLETED status and a non-empty failed_reason."""
    asyncio.run(_full_workflow_with_rejection())


async def _full_workflow_with_rejection():
    llm_reasoning = get_reasoning_llm()
    llm_chat = get_chat_llm()
    alert = ManagedMockClient.load_alert_payload(FIXTURE_PATH)

    async with AsyncExitStack() as stack:
        mcp_read = await stack.enter_async_context(ManagedMockClient(FIXTURE_PATH, "read"))
        mcp_write = await stack.enter_async_context(ManagedMockClient(FIXTURE_PATH, "write"))
        graph = build_graph(llm_reasoning, llm_chat, mcp_read, mcp_write)
        config = _make_config()

        await _stream_graph(graph, _make_initial_state(alert), config)

        snapshot = graph.get_state(config)
        if NodeName.EXECUTION not in snapshot.next:
            pytest.skip(
                f"Workflow did not reach planning stage "
                f"(status={snapshot.values.get('workflow_status')}); skipping."
            )

        graph.update_state(config, {
            "approval_decision": ApprovalDecision.REJECTED,
            "human_feedback": "Rejected by automated test — manual override needed.",
        })
        await _stream_graph(graph, None, config)

        final = graph.get_state(config)
        final_status = final.values.get("workflow_status")
        assert final_status == WorkflowStatus.COMPLETED.value, (
            f"Rejected workflow should end as COMPLETED, got {final_status}"
        )
        assert final.values.get("failed_reason"), "failed_reason must be set when DBA rejects the plan"
        logger.info("rejection path finished with failed_reason=%s", final.values.get("failed_reason"))
