from datetime import timedelta, datetime, timezone
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
import jwt
from jwt.exceptions import InvalidTokenError

from graphdba.config.settings import get_settings

password_hasher = PasswordHasher(type=Type.ID)
security_settings = get_settings().security

def hash_password(password: str) -> str:
    return password_hasher.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False

def encode_access_token(*, user_id: int, employee_id: str, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + (expires_delta or timedelta(minutes=security_settings.access_token_expire_mins))
    payload = {
        "sub": str(user_id),
        "employee_id": employee_id,
        "iat": now,
        "exp": expires_at,
        "type": "access",
    }
    return jwt.encode(
        payload, 
        security_settings.secret_key, 
        algorithm=security_settings.secret_algorithm,
    )

def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        security_settings.secret_key,
        algorithms=[security_settings.secret_algorithm],
    )
    if payload.get("type") != "access":
        raise InvalidTokenError("Invalid token type")
    if not payload.get("sub"):
        raise InvalidTokenError("Token missing subject")
    return payload
