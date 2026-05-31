import uuid
from typing import Any
from enum import StrEnum
from datetime import datetime
from pydantic import BaseModel, Field

# Read Models
class ExplainQueryInput(BaseModel):
    query: str = Field(description="The read-only PostgreSQL query to analyze")
    run_analyze: bool = Field(default=False, description="set True to execute the explain query")

class SlowQueryFilter(BaseModel):
    limit: int = Field(default=100, description="Number of queries to return")
    min_duration_ms: int = Field(default=1000, description="Minimum query duration in ms")

class SafeSelectInput(BaseModel):
    query: str = Field(description="The SELECT query to execute")

# Write Models
# 1. TABLE alerts
class AlertStatus(StrEnum):
    RECEIVED = "RECEIVED"
    RUNNING = "RUNNING"
    WAITING = "WAITING_APPROVAL"
    SOLVED = "SOLVED"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"

class AlertResponse(BaseModel):
    model_config = {"from_attributes": True}

    alert_id: uuid.UUID
    fingerprint: str
    alertname: str
    severity: str
    instance: str | None
    alert_summary: str
    description: str | None
    raw_payload: dict[str, Any]
    status: AlertStatus
    escalation_reason: str | None
    failure_reason: str | None
    started_at: datetime | None
    received_at: datetime
    updated_at: datetime
    solved_at: datetime | None
    resolved_at: datetime | None

class CreateAlertInput(BaseModel):
    fingerprint: str = Field(description="Unique Alertmanager fingerprint")
    alertname: str = Field(description="Alert name")
    severity: str = Field(description="Alert severity")
    instance: str | None = Field(default=None, description="Alert source instance")
    alert_summary: str = Field(description="Human-readable alert summary")
    description: str | None = Field(default=None, description="Detailed alert description")
    # raw_payload: dict[str, Any] = Field(default_factory=dict, description="Original alert payload")
    started_at: datetime | None = Field(default=None, description="Alert start timestamp")

class UpdateAlertStatusInput(BaseModel):
    alert_id: uuid.UUID = Field(description="Alert UUID to update")
    status: AlertStatus = Field(description="New alert workflow status")
    escalation_reason: str | None = Field(default=None, description="Reason for escalation, when status is ESCALATED")
    solved_at: datetime | None = Field(default=None, description="Solved timestamp, when status is SOLVED")
    resolved_at: datetime | None = Field(default=None, description="External resolved timestamp")
    failure_reason: str | None = Field(default=None, description="Reason for failure, when status is FAILED")
    clear_failure_reason: bool = Field(default=False, description="Set True to wipe failure reason")
    

# 3. TABLE tickets
class TicketStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ROLLBACK = "ROLLED_BACK"

class ProposeActionInput(BaseModel):
    alert_fingerprint: str = Field(description="The alert fingerprint this ticket addresses")
    alert_payload: dict = Field(description="Full alert payload for audit context")
    hypotheses: list[dict] = Field(description="Validated hypotheses that led to this plan")
    hypotheses_id: str = Field(description="ID of the hypothesis this plan addresses")
    agent_steps: list[dict] = Field(description="Ordered execution steps, each with step_order, step_name, and action_sql")
    change_reason: str = Field(description="Reason for the change")
    rollback_sql: str | None = Field(default=None, description="Rollback SQL")
    risk_level: str = Field(default="MEDIUM", description="Risk Level: LOW, MEDIUM, HIGH, CRITICAL")
    
class UpdateTicketInput(BaseModel):
    oauth_token: str = Field(description="The JWT token of the approving DBA")
    ticket_id: str = Field(description="The ID of the ticket to approve")
    modified_sql: str | None = Field(default=None, description="Optional modified SQL provided by MODIFIED")
    ticket_status: TicketStatus = Field(description="Only APPROVED or REJECTED allowed")
    approval_comments: str | None = Field(default=None, description="Optional approval comments")
