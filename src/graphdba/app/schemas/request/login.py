from pydantic import BaseModel

class LoginRequest(BaseModel):
    employee_id: str
    password: str