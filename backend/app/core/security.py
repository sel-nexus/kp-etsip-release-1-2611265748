"""Hash off-loop and issue/validate eight-hour signed bearer claims."""
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError
from app.core.config import Settings
from app.core.errors import DomainError
from app.features.auth.schemas import TokenClaims, Session

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


async def hash_password(password: str) -> str:
    """Hash a bounded password without blocking the application event loop."""
    if not 12 <= len(password.encode("utf-8")) <= 72:
        raise ValueError("Password must contain 12–72 UTF-8 bytes")
    return await asyncio.to_thread(password_context.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    """Verify a bounded password, treating corrupt stored hashes as invalid."""
    if not 1 <= len(password.encode("utf-8")) <= 72:
        return False
    try:
        return await asyncio.to_thread(password_context.verify, password, password_hash)
    except (ValueError, TypeError):
        return False


def create_token(user_id: str, role: str, version: int, settings: Settings) -> str:
    """Sign identity and revocation claims with the configured lifetime."""
    now = datetime.now(UTC)
    claims = TokenClaims(sub=user_id, userId=user_id, role=role, tokenVersion=version,
                         iat=int(now.timestamp()), exp=int((now + timedelta(hours=settings.JWT_EXPIRY_HOURS)).timestamp()),
                         jti=uuid4().hex)
    return jwt.encode(claims.model_dump(), settings.JWT_SECRET.get_secret_value(), algorithm="HS256")


def decode_token(token: str, settings: Settings) -> TokenClaims:
    """Reject invalid signatures, expiration, identifiers, or claim shapes."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET.get_secret_value(), algorithms=["HS256"],
                             options={"require_exp": True, "require_sub": True, "require_iat": True})
        claims = TokenClaims.model_validate(payload)
        if claims.sub != claims.userId or claims.iat > int(datetime.now(UTC).timestamp()):
            raise ValueError("Invalid claims")
        if claims.exp <= int(datetime.now(UTC).timestamp()):
            raise ValueError("Expired token")
        return claims
    except (JWTError, ValidationError, ValueError, TypeError) as exc:
        raise DomainError(401, "Invalid or expired session") from exc


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Session:
    """Resolve the live active session without trusting JWT role permissions."""
    if credentials is None:
        raise DomainError(401, "Authentication required")
    return await request.app.state.auth.authenticate(credentials.credentials)
