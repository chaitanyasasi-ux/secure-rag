from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from app.core.config import get_settings
from app.core.roles import RoleLevel

settings = get_settings()

# ── Token payload schema ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TokenPayload:
    """
    Decoded, validated JWT payload.  Immutable — downstream code cannot mutate it.
    Passed as the resolved dependency type throughout the app.
    """

    sub: str          # user_id (UUID string)
    role: str         # human-readable role name
    role_level: int   # RoleLevel integer — used directly in Qdrant filter
    department: str   # department slug (e.g. "engineering", "finance")
    jti: str          # JWT ID — used for token revocation (Day 6)
    exp: datetime
    iat: datetime

    @property
    def user_id(self) -> str:
        return self.sub

    @property
    def role_enum(self) -> RoleLevel:
        return RoleLevel(self.role_level)


# ── Token creation ────────────────────────────────────────────────────────────


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    *,
    user_id: str,
    role: str,
    role_level: int,
    department: str,
    expires_delta: timedelta | None = None,
) -> str:
    expire = _utc_now() + (
        expires_delta
        or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "role_level": role_level,
        "department": department,
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "iat": _utc_now(),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(*, user_id: str) -> str:
    expire = _utc_now() + timedelta(days=settings.refresh_token_expire_days)
    payload: dict[str, Any] = {
        "sub": user_id,
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "iat": _utc_now(),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# ── Token decoding ────────────────────────────────────────────────────────────


class TokenExpiredError(Exception):
    pass


class TokenInvalidError(Exception):
    pass


def decode_access_token(token: str) -> TokenPayload:
    """
    Decode and validate an access token.  Raises typed exceptions — never raw JWTError.
    """
    try:
        raw: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token has expired.") from exc
    except JWTError as exc:
        raise TokenInvalidError(f"Token validation failed: {exc}") from exc

    if raw.get("type") != "access":
        raise TokenInvalidError("Provided token is not an access token.")

    return TokenPayload(
        sub=raw["sub"],
        role=raw["role"],
        role_level=int(raw["role_level"]),
        department=raw["department"],
        jti=raw["jti"],
        exp=datetime.fromtimestamp(raw["exp"], tz=timezone.utc),
        iat=datetime.fromtimestamp(raw["iat"], tz=timezone.utc),
    )


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Returns raw payload dict — only sub and jti matter for refresh flow."""
    try:
        raw = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Refresh token has expired.") from exc
    except JWTError as exc:
        raise TokenInvalidError(f"Refresh token validation failed: {exc}") from exc

    if raw.get("type") != "refresh":
        raise TokenInvalidError("Provided token is not a refresh token.")

    return raw
