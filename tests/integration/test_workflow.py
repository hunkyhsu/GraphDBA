from __future__ import annotations
import asyncio
import logging
from uuid import uuid4
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

from graphdba.agents.graph import build_graph
from graphdba.agents.state import FinalPlan, WorkflowStatus
from graphdba.config.dependencies import get_reasoning_llm, get_chat_llm
from tests.conftest import ManagedMockClient

if TYPE_CHECKING:
    from graphdba.agents.state import AgentStateUpdate

logger = logging.getLogger(__name__)

FIXTURE_PATH = "tests/data/deadlock_sample.yaml"


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_config() -> dict:
    return {"configurable": {"thread_id": f"test_{uuid4().hex[:8]}"}}


class FakeEmbeddings:
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def _make_initial_state(alert: dict) -> AgentStateUpdate:
    if "id" not in alert:
        alert = {**alert, "id": alert.get("fingerprint", "test_alert")}
    return {
        "alert": alert,
        "workflow_status": WorkflowStatus.TRIAGED.value,
        "attempt_count": 0,
        "current_hypotheses": [],
        "rejected_hypotheses": [],
        "final_plan": None,
        "ticket_id": None,
        "approval_decision": None,
        "human_feedback": None,
        "terminal_message": None,
    }


async def _stream_graph(graph, initial_state: dict | None, config: dict) -> None:
    async for event in graph.astream(initial_state, config):
        for node_name, state_update in event.items():
            logger.debug("node=%s status=%s", node_name, state_update.get("workflow_status", "—"))


# ── integration: full workflow (requires LLM API credentials in .env) ─────────

def test_full_workflow_reaches_planning():
    """Graph must stop with a valid FinalPlan after planning."""
    asyncio.run(_full_workflow_reaches_planning())


async def _full_workflow_reaches_planning():
    llm_reasoning = get_reasoning_llm()
    llm_chat = get_chat_llm()
    alert = ManagedMockClient.load_alert_payload(FIXTURE_PATH)

    async with AsyncExitStack() as stack:
        mcp_read = await stack.enter_async_context(ManagedMockClient(FIXTURE_PATH, "read"))
        graph = build_graph(llm_reasoning, llm_chat, FakeEmbeddings(), mcp_read)
        config = _make_config()

        await _stream_graph(graph, _make_initial_state(alert), config)

        snapshot = graph.get_state(config)
        assert not snapshot.next, f"Graph should finish at planning; next={snapshot.next}"
        status = snapshot.values.get("workflow_status")
        assert status == WorkflowStatus.PLANNED.value, f"Expected PLANNED, got {status}"

        raw_plan = snapshot.values.get("final_plan")
        assert raw_plan is not None, "final_plan must be populated before the interrupt"
        plan = FinalPlan.model_validate(raw_plan)
        assert plan.execution_steps, "final_plan must contain at least one execution step"
        assert plan.target_alert_id == "alert_deadlock_001"
