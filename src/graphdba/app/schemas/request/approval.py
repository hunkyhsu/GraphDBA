from pydantic import BaseModel, model_validator
from graphdba.agents.state import ApprovalDecision

class ApprovalRequest(BaseModel):
    decision: ApprovalDecision
    modified_sql: str | None = None
    feedback: str | None = None
    @model_validator(mode="after")
    def validate_logic(self):
        if self.decision == ApprovalDecision.REJECTED and not self.feedback:
            raise ValueError("Rejected MUST provide feedback")
        return self