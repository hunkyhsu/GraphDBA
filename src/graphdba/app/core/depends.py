from typing import cast, Any
import asyncpg
import jwt
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from langgraph.graph.state import CompiledStateGraph
from mcp.client.session import ClientSession

from graphdba.config.settings import get_settings


def get_graph(request: Request) -> CompiledStateGraph:
    return cast(CompiledStateGraph, request.app.state.graph)

def get_mcp_read(request: Request) -> ClientSession:
    return cast(ClientSession, request.app.state.mcp_read)

def get_mcp_write(request: Request) -> ClientSession:
    return cast(ClientSession, request.app.state.mcp_write)

def get_pool(request: Request) -> asyncpg.Pool:
    return cast(asyncpg.Pool, request.app.state.pool)

security_schema = HTTPBearer()

async def get_raw_token(credentials: HTTPAuthorizationCredentials = Depends(security_schema)) -> str:
    return credentials.credentials

async def get_verified_token(credentials: HTTPAuthorizationCredentials = Depends(security_schema)) -> dict[str, Any]:
    """Validates JWT signature and expiry; raises 401 on failure."""
    try:
        settings = get_settings()
        payload = jwt.decode(credentials.credentials, settings.security.oauth_secret, algorithms=["HS256"])
        if not payload.get("pg_role"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing role claim")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")