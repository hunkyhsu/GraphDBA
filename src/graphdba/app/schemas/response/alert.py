from pydantic import BaseModel

class AlertsStateResponse(BaseModel):
    run_id: str
    status: str