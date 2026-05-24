import logging
import jwt
import asyncpg
import uuid
from typing import Any
from graphdba.config.settings import get_settings
from graphdba.utils.external_call import db_readonly_fetch

logger = logging.getLogger(__name__)

class WriteSecurityError(ValueError):
    """Custom exception for unauthorized or out-of-bounds write attempts."""
    pass

def verify_identity(token: str) -> dict[str, Any]:
    """Decodes the OAuth JWT and extracts the DBA's Postgres role."""
    if not token or not isinstance(token, str):
        raise WriteSecurityError("Token is missing or invalid type")
    try:
        OAUTH_SECRET = get_settings().security.oauth_secret
        payload = jwt.decode(token, OAUTH_SECRET, algorithms=["HS256"])
        dba_role = payload.get("pg_role")
        if not dba_role:
            raise WriteSecurityError("Authentication role missing")
        logger.info("Identity verified. Agent acting on behalf of DBA role: %s", dba_role)
        return payload
    except WriteSecurityError:
        raise
    except jwt.ExpiredSignatureError:
        raise WriteSecurityError("OAuth token has expired. Human re-authentication required.")
    except jwt.InvalidTokenError:
        raise WriteSecurityError("Invalid OAuth token.")
    except Exception:
        logger.exception("Unexpected error during token verification")
        raise WriteSecurityError("Internal authentication error")

async def validate_sql_syntax(pool: asyncpg.Pool, sql: str) -> None:
    """Validate Syntax"""
    if not sql or not sql.strip():
        raise WriteSecurityError("SQL cannot be empty")
    if sql.strip().rstrip(";").count(";") > 0:
        raise WriteSecurityError("Multiple SQL statements are not support")
    
    async def _do_prepare(conn: asyncpg.Connection) -> bool:
        statement_name = f"mcp_validate_{uuid.uuid4().hex[:8]}"
        await conn.execute(f"PREPARE {statement_name} AS {sql}")
        await conn.execute(f"DEALLOCATE {statement_name}")
        return True
    _, error = await db_readonly_fetch(
        pool=pool,
        query_fn=_do_prepare,
        label="SQL Syntax Validation",
        logger=logger,
    )
    if error:
        if "syntax error" in error.lower() or "42601" in error:
            raise WriteSecurityError(f"SQL syntax error: {error}")
        raise WriteSecurityError(f"SQL validation failed: {error}")