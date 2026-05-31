from pydantic import BaseModel

from graphdba.app.schemas.response.login import LoginRole, LoginUser


class MeResponse(BaseModel):
    user: LoginUser
    roles: list[LoginRole]