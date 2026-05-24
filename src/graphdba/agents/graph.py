from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from graphdba.agents.state import AgentState, NodeName, WorkflowStatus
from graphdba.agents.triage import triage_node
from graphdba.agents.diagnostic import DiagnosticNode
from graphdba.agents.validation import ValidationNode
from graphdba.agents.planning import PlanningNode
from graphdba.agents.proposing import ProposingNode
from graphdba.agents.execution import ExecutionNode
from graphdba.config.settings import get_settings

if TYPE_CHECKING:
    from mcp.client.session import ClientSession
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

def route_triage(state: AgentState) -> str:
    """Where to go AFTER Triage Node"""
    status: WorkflowStatus = state["workflow_status"]
    if status == WorkflowStatus.TRIAGED:
        return NodeName.DIAGNOSTIC
    # else condition include: FAILED, COMPLETED
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

def route_planning(state: AgentState) -> str:
    """Where to go AFTER Planning Node"""
    status: WorkflowStatus = state["workflow_status"]
    if status == WorkflowStatus.PLANNED:
        return NodeName.PROPOSING
    # else condition include: FAILED (human escalation or errors all considered as FAILED)
    return END

def route_proposing(state: AgentState) -> str:
    """Where to go AFTER Proposing Node"""
    status: WorkflowStatus = state["workflow_status"]
    if status == WorkflowStatus.PROPOSED:
        return NodeName.EXECUTION
    return END

def build_graph(
        llm_reasoning: BaseChatModel,
        llm_chat: BaseChatModel,
        embedding: HuggingFaceEmbeddings,
        mcp_read_client: ClientSession,
        mcp_write_client: ClientSession
    ):
    logger.info("Starting to orchestrate the graph state...")
    builder = StateGraph(AgentState)
    # 1. nodes
    builder.add_node(NodeName.TRIAGE, triage_node)
    builder.add_node(NodeName.DIAGNOSTIC, DiagnosticNode(llm=llm_reasoning, mcp_client=mcp_read_client, embeddings=embedding))
    builder.add_node(NodeName.VALIDATION, ValidationNode(llm=llm_chat, mcp_client=mcp_read_client))
    builder.add_node(NodeName.PLANNING, PlanningNode(llm=llm_reasoning))
    builder.add_node(NodeName.PROPOSING, ProposingNode(mcp_client=mcp_write_client))
    builder.add_node(NodeName.EXECUTION, ExecutionNode(mcp_client=mcp_write_client))
    # 2. edges
    builder.add_edge(START, NodeName.TRIAGE)

    builder.add_conditional_edges(NodeName.TRIAGE, route_triage)
    builder.add_conditional_edges(NodeName.DIAGNOSTIC, route_diagnostic)
    builder.add_conditional_edges(NodeName.VALIDATION, route_validation)
    builder.add_conditional_edges(NodeName.PLANNING, route_planning)
    builder.add_conditional_edges(NodeName.PROPOSING, route_proposing)

    builder.add_edge(NodeName.EXECUTION, END)

    # In production, use AsyncPostgresSaver to save to database
    memory = MemorySaver()
    graph = builder.compile(
        checkpointer=memory,
        interrupt_before=[NodeName.EXECUTION]
    )
    logger.info("Orchestration completed")
    return graph

