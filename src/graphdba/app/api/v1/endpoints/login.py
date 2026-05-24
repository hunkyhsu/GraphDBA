from datetime import datetime, timedelta, timezone
import logging
import asyncpg
import jwt
from fastapi import APIRouter, status, HTTPException
from asyncpg.exceptions import PostgresError, InvalidPasswordError, InvalidAuthorizationSpecificationError

from graphdba.app.schemas.request.login import LoginRequest
from graphdba.app.schemas.response.login import LoginResponse
from graphdba.config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", status_code=status.HTTP_200_OK, response_model=LoginResponse)
async def login(
    body: LoginRequest,
):
    settings = get_settings()
    database_settings = settings.database
    temporary_connection: asyncpg.Connection | None = None
    try:
        temporary_connection = await asyncpg.connect(
            host=database_settings.host,
            port=database_settings.port,
            database=database_settings.db,
            user=body.database_role,
            password=body.database_password,
            timeout=database_settings.connection_timeout,
        )
    except (InvalidAuthorizationSpecificationError, InvalidPasswordError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Database authentication failed. Invalid role name or password.",
        )
    except (PostgresError, OSError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database cluster unreachable: {type(e).__name__}",
        )
    finally:
        if temporary_connection:
            await temporary_connection.close()
    now = datetime.now(timezone.utc)
    token_payload = {
        "pg_role": body.database_role,
        "exp": now + timedelta(hours=2),
        "iat": now,
    }
    token = jwt.encode(token_payload, settings.security.oauth_secret, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer"}