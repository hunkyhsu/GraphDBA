from pydantic import BaseModel

class ApproveResponse(BaseModel):
    run_id: str
    status: str