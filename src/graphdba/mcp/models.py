from enum import StrEnum
from pydantic import BaseModel, Field

# read models
class ExplainQueryInput(BaseModel):
    query: str = Field(description="The read-only PostgreSQL query to analyze")
    run_analyze: bool = Field(default=False, description="set True to execute the explain query")

class SlowQueryFilter(BaseModel):
    limit: int = Field(default=100, description="Number of queries to return")
    min_duration_ms: int = Field(default=1000, description="Minimum query duration in ms")

class SafeSelectInput(BaseModel):
    query: str = Field(description="The SELECT query to execute")

# write models
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
    
class ExecuteActionInput(BaseModel):
    ticket_id: str = Field(description="The ID of the human-approved tuning ticket.")

class UpdateTicketInput(BaseModel):
    oauth_token: str = Field(description="The JWT token of the approving DBA")
    ticket_id: str = Field(description="The ID of the ticket to approve")
    modified_sql: str | None = Field(default=None, description="Optional modified SQL provided by MODIFIED")
    ticket_status: TicketStatus = Field(description="Only APPROVED or REJECTED allowed")
    approval_comments: str | None = Field(default=None, description="Optional approval comments")
