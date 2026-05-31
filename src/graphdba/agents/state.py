import operator
from enum import StrEnum
from uuid import uuid4
from typing import Annotated, Literal, TypedDict, List, Any
from pydantic import BaseModel, Field

# Data Model(Schema)
class AlertPayload(BaseModel):
    """Schema of alert"""
    id: str = Field(description="Unique identity of an alert")
    name: str = Field(alias="alertname", description="The structured name of an alert(brief name)")
    instance: str = Field(description="Address of alerted database (IP:Port)")
    summary: str = Field(description="Summary of an alert")
    description: str = Field(description="Detail of an alert")
    # raw_payload: dict[str, Any] = Field(description="Other messages from alert manager")

class ValidationAction(BaseModel):
    tool_name: str = Field(description="MCP tool name for validation")
    tool_payload: dict[str, Any] = Field(description="MCP tool JSON payload")

class HypothesisStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"

class Hypothesis(BaseModel):
    """Schema of hypothesis for diagnostic node"""
    id: str = Field(default_factory=lambda: f"HYP_{uuid4().hex[:8].upper()}", description="Unique identity of a hypothesis")
    root_cause: str = Field(description="1 sentence description of a hypothesis about the root cause")
    # description: list[str] = Field(description="Detail description of a hypothesis")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence score for a hypothesis by AI")
    validation_actions: list[ValidationAction] = Field(description="SQL used to validate a hypothesis")
    expected_result: str = Field(description="Expected result when execute the validation SQL to prove a hypothesis")
    status: HypothesisStatus = Field(default=HypothesisStatus.PENDING, description="The status of a hypothesis")
    feedback: str | None = Field(default=None, description="Feedback from validation node when a hypothesis is rejected")

class Feedback(BaseModel):
    """Schema of feedback for validation node"""
    hypothesis_id: str = Field(description="Unique identity of a hypothesis")
    is_validated: bool = Field(description="True for verified, False for rejected in Hypothesis.status")
    actual_result: str = Field(description="Validation result after using MCP tools")
    reasoning: str = Field(description="Reasons for the validation result and direct to Hypothesis.feedback")

class PlanStep(BaseModel):
    step_order: int = Field(description="Step order")
    # step_name: str = Field(description="Step name")
    action_sql: str = Field(description="Exact action SQL")

class PlanRiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class FinalPlan(BaseModel):
    """Schema of final execution plan for planning node"""
    target_alert_id: str = Field(description="Unique identity of a alert need to execute")
    target_hypothesis_id: str = Field(description="Unique identity of a validated hypothesis")
    # fix_summary: str = Field(description="Summary of the fix plan")
    change_reason: str = Field(description="Detail of the change reason, as the description of ticket")
    risk_level: PlanRiskLevel = Field(description="Severity level of the fix plan")
    execution_steps: list[PlanStep] = Field(description="Execution plan steps")
    rollback_sql: str | None = Field(default=None, description="Rollback SQL")
    rollback_note: str | None = Field(default=None, description="Explain why rollback SQL is not applicable")

class WorkflowStatus(StrEnum):
    TRIAGED = "triaged"
    DIAGNOSED = "diagnosed"
    VALIDATED_SUCCESS = "validated_success"
    VALIDATED_FAIL = "validated_fail"
    PLANNED = "planned"
    PROPOSED = "proposed"
    EXECUTED = "executed"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"

class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"

# Global State
class AgentState(TypedDict):
    """The shared memory for Multi-Agent State Machine"""
    alert: dict
    # Hypothesis in current loop, can be replace next loop
    current_hypotheses: list[dict]
    # Rejected hypothesis used for retry, should append only during the loop
    rejected_hypotheses: Annotated[list[dict], operator.add]
    final_plan: dict | None
    ticket_id: str | None
    attempt_count: int
    workflow_status: str
    approval_decision: str | None
    # Feedback of human DBA when approval decision = rejected or modified
    human_feedback: str | None
    terminal_message: str | None

class AgentStateUpdate(AgentState, total=False): 
    """Partial update for AgentState""" 
    pass

class AgentStateValues(BaseModel):
    """The shared memory for Multi-Agent State Machine"""
    alert: AlertPayload
    current_hypotheses: list[Hypothesis]
    rejected_hypotheses: list[Hypothesis]
    final_plan: FinalPlan | None = None
    ticket_id: str | None = None
    attempt_count: int
    workflow_status: str
    approval_decision: str | None = None
    human_feedback: str | None = None
    terminal_message: str | None = None

class NodeName(StrEnum):
    TRIAGE = "triage_node"
    DIAGNOSTIC = "diagnostic_node"
    VALIDATION = "validation_node"
    PLANNING = "planning_node"
    PROPOSING = "proposing_node"
    EXECUTION = "execution_node"