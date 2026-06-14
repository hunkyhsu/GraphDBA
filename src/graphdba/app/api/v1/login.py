from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.app.core.security import encode_access_token, verify_password
from graphdba.app.schemas.request.login import LoginRequest
from graphdba.app.schemas.response.login import LoginResponse
from graphdba.database.repositories import user_roles, users
from graphdba.database.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("", status_code=status.HTTP_200_OK, response_model=LoginResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    user = await users.get_user_by_employee_id(session, body.employee_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid employee ID.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )

    now = datetime.now(timezone.utc)
    if user.locked_until is not None and user.locked_until > now:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="User account is temporarily locked.",
        )

    if not verify_password(body.password, user.password_hash):
        await users.record_failed_login(session, user)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password.",
        )

    await users.reset_login_failures(session, user)
    roles = await user_roles.list_roles_for_user(session, user.id)
    await session.commit()

    token = encode_access_token(
        user_id=user.id,
        employee_id=user.employee_id,
    )
    logger.info("User %s logged in successfully", user.employee_id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "employee_id": user.employee_id,
            "name": user.name,
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
