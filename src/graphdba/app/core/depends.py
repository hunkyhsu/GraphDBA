from typing import cast, Any
import asyncpg
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from graphdba.app.core.security import decode_access_token
from graphdba.agents.container import AgentContainer
from graphdba.database.models.user import User
from graphdba.database.repositories import users
from graphdba.database.session import get_session


def get_agent_container(request: Request) -> AgentContainer:
    return cast(AgentContainer, request.app.state.agent_container)


async def get_graph(request: Request) -> CompiledStateGraph:
    return await get_agent_container(request).get_graph()


def get_pool(request: Request) -> asyncpg.Pool:
    return cast(asyncpg.Pool, request.app.state.pool)

security_schema = HTTPBearer()

async def get_raw_token(credentials: HTTPAuthorizationCredentials = Depends(security_schema)) -> str:
    return credentials.credentials

async def get_verified_token(credentials: HTTPAuthorizationCredentials = Depends(security_schema)) -> dict[str, Any]:
    """Validates JWT signature and expiry; raises 401 on failure."""
    try:
        return decode_access_token(credentials.credentials)
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(
    token_payload: dict[str, Any] = Depends(get_verified_token),
    session: AsyncSession = Depends(get_session),
) -> User:
    user_id = token_payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject")

    try:
        parsed_user_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    user = await users.get_user_by_id(session, parsed_user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
    return user
