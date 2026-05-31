from pydantic import BaseModel

class LoginRole(BaseModel):
    id: int
    name: str
    type: str

class LoginUser(BaseModel):
    id: int
    employee_id: str
    name: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: LoginUser
    roles: list[LoginRole]