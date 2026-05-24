from pydantic import BaseModel

class LoginRequest(BaseModel):
    database_role: str
    database_password: str