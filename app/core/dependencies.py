"""
Dependency injection layer.

Usage in route:
    @router.get("/admin-only")
    async def admin_route(
        payload: TokenPayload = Depends(require_role(RoleLevel.ADMIN)),
    ):
        ...

    @router.get("/me")
    async def me(payload: TokenPayload = Depends(get_current_active_user)):
        ...
"""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.roles import RoleLevel
from app.core.security import (
    TokenExpiredError,
    TokenInvalidError,
    TokenPayload,
    decode_access_token,
)
from app.db.session import AsyncSession, get_db
from app.models.user import User
from sqlmodel import select

log = structlog.get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def _extract_token_payload(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> TokenPayload:
    """
    Extract and decode the Bearer JWT from the Authorization header.
    Raises 401 on any failure — never 403 at this stage.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_access_token(credentials.credentials)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    payload: Annotated[TokenPayload, Depends(_extract_token_payload)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> tuple[TokenPayload, User]:
    """
    Resolves the JWT payload AND the live User row.
    Returns both so endpoints can access either without extra DB calls.
    """
    result = await db.execute(select(User).where(User.id == payload.user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )
    return payload, user


async def get_current_active_user(
    ctx: Annotated[tuple[TokenPayload, User], Depends(get_current_user)],
) -> TokenPayload:
    """
    Simplified dependency that returns only the TokenPayload.
    Use this when you only need identity claims without the User ORM object.
    """
    payload, _ = ctx
    return payload


def require_role(minimum_level: RoleLevel):
    """
    Factory that returns a dependency enforcing a minimum role level.

    Example:
        Depends(require_role(RoleLevel.MANAGER))

    Raises 403 if the authenticated user's role level is below the minimum.
    """

    async def _check(
        payload: Annotated[TokenPayload, Depends(get_current_active_user)],
    ) -> TokenPayload:
        if payload.role_level < minimum_level:
            log.warning(
                "rbac.access_denied",
                user_id=payload.user_id,
                user_role_level=payload.role_level,
                required_level=minimum_level,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum_level.name} role or higher.",
            )
        return payload

    return _check


# ── Convenience aliases ───────────────────────────────────────────────────────

RequireEmployee = Depends(require_role(RoleLevel.EMPLOYEE))
RequireManager = Depends(require_role(RoleLevel.MANAGER))
RequireAdmin = Depends(require_role(RoleLevel.ADMIN))
