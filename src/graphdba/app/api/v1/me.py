from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.app.core.depends import get_current_user
from graphdba.database.models.user import User
from graphdba.database.repositories import user_roles
from graphdba.database.session import get_session
from graphdba.app.schemas.response.me import MeResponse


router = APIRouter()


@router.get("/me", response_model=MeResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    roles = await user_roles.list_roles_for_user(session, current_user.id)
    return {
        "user": {
            "id": current_user.id,
            "employee_id": current_user.employee_id,
            "name": current_user.name,
        },
        "roles": [
            {
                "id": role.id,
                "name": role.name,
                "type": role.type,
            }
            for role in roles
        ],
    }
