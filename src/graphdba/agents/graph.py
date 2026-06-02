from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from graphdba.agents.state import AgentState, NodeName, WorkflowStatus
from graphdba.agents.diagnostic import DiagnosticNode
from graphdba.agents.validation import ValidationNode
from graphdba.agents.planning import PlanningNode
from graphdba.config.settings import get_settings

if TYPE_CHECKING:
    from mcp.client.session import ClientSession
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

def route_start(state: AgentState) -> str:
    """Route initialized alert state into the graph or finish terminal fast paths."""
    status: WorkflowStatus = state["workflow_status"]
    if status == WorkflowStatus.TRIAGED:
        return NodeName.DIAGNOSTIC
    return END

def route_diagnostic(state: AgentState) -> str:
    """Where to go AFTER Diagnostic Node"""
    status: WorkflowStatus = state["workflow_status"]
    if status == WorkflowStatus.DIAGNOSED:
        return NodeName.VALIDATION
    # else condition include: FAILED (human escalation or errors all considered as FAILED)
    return END

def route_validation(state: AgentState) -> str:
    """Where to go AFTER Diagnostic Node"""
    status: WorkflowStatus = state["workflow_status"]
    if status == WorkflowStatus.VALIDATED_SUCCESS:
        return NodeName.PLANNING
    elif status == WorkflowStatus.VALIDATED_FAIL:
        attempt_count = state.get("attempt_count", 0)
        if attempt_count < get_settings().agent.max_retries:
            logger.warning("Validation failed, retry the %d times", attempt_count + 1)
            return NodeName.DIAGNOSTIC
        else:
            logger.error("Maximum number of attempts reached. Can not attempt again")
            return END
    # else condition include: FAILED (errors all considered as FAILED)
    return END

def build_graph(
        llm_reasoning: BaseChatModel,
        llm_chat: BaseChatModel,
        embedding: HuggingFaceEmbeddings,
        mcp_read_client: ClientSession,
    ):
    logger.info("Starting to orchestrate the graph state...")
    builder = StateGraph(AgentState)
    # 1. nodes
    builder.add_node(NodeName.DIAGNOSTIC, DiagnosticNode(llm=llm_reasoning, mcp_client=mcp_read_client, embeddings=embedding))
    builder.add_node(NodeName.VALIDATION, ValidationNode(llm=llm_chat, mcp_client=mcp_read_client))
    builder.add_node(NodeName.PLANNING, PlanningNode(llm=llm_reasoning))
    # 2. edges
    builder.add_conditional_edges(START, route_start)
    builder.add_conditional_edges(NodeName.DIAGNOSTIC, route_diagnostic)
    builder.add_conditional_edges(NodeName.VALIDATION, route_validation)
    builder.add_edge(NodeName.PLANNING, END)

    # In production, use AsyncPostgresSaver to save to database
    memory = MemorySaver()
    graph = builder.compile(checkpointer=memory)
    logger.info("Orchestration completed")
    return graph
