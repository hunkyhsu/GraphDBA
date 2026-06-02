from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TicketAlertSummary(BaseModel):
    alert_id: UUID
    alertname: str
    severity: str
    status: str
    instance: str | None = None
    cluster_name: str | None = None
    database_name: str | None = None
    database_role: str | None = None
    summary: str
    started_at: datetime | None = None
    updated_at: datetime
    thread_id: str | None = None


class TicketHypothesisSummary(BaseModel):
    hypothesis_id: str
    root_cause: str
    status: str
    confidence_score: float
    feedback: str | None = None
    metric_evidence: dict[str, Any] = Field(default_factory=dict)


class TicketListItem(BaseModel):
    ticket_id: UUID
    alert_id: UUID
    run_id: str | None = None
    alertname: str
    instance: str | None = None
    status: str
    risk_level: str
    change_reason: str
    created_at: datetime
    updated_at: datetime


class TicketListResponse(BaseModel):
    items: list[TicketListItem]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class TicketDetailResponse(BaseModel):
    ticket_id: UUID
    alert_id: UUID
    run_id: str | None = None
    hypothesis_id: str
    status: str
    risk_level: str
    created_at: datetime
    updated_at: datetime
    proposed_steps: list[dict[str, Any]]
    approved_steps: list[dict[str, Any]] | None = None
    change_reason: str
    rollback_sql: str | None = None
    rollback_note: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_comments: str | None = None
    executed_at: datetime | None = None
    execution_duration_ms: int | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    alert: TicketAlertSummary
    hypotheses: list[TicketHypothesisSummary] = Field(default_factory=list)
