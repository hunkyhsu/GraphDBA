from pydantic import BaseModel
from graphdba.agents.state import AgentStateValues

class RunStateResponse(BaseModel):
    run_id: str
    values: AgentStateValues
    next: list[str]