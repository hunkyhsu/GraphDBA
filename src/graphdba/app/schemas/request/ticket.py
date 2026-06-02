from typing import Any

from pydantic import BaseModel, Field, model_validator


class TicketStepUpdate(BaseModel):
    step_order: int = Field(ge=1)
    action_sql: str = Field(min_length=1)
    title: str | None = None
    description: str | None = None


class TicketPlanUpdateRequest(BaseModel):
    change_reason: str = Field(min_length=1)
    proposed_steps: list[TicketStepUpdate] = Field(min_length=1)
    rollback_sql: str | None = None
    rollback_note: str | None = None
    human_notes: str | None = None
    pre_execution_notes: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_rollback(self):
        if bool(self.rollback_sql and self.rollback_sql.strip()) == bool(
            self.rollback_note and self.rollback_note.strip()
        ):
            raise ValueError("Provide exactly one of rollback_sql or rollback_note")
        return self
