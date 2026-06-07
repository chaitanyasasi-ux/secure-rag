from __future__ import annotations

from datetime import datetime, timedelta

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.hashing import hash_password, verify_password
from app.core.security import (
    TokenExpiredError,
    TokenInvalidError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.models.user import RefreshToken, Role, User
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse

log = structlog.get_logger(__name__)
settings = get_settings()


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def signup(self, payload: SignupRequest) -> User:
        result = await self._db.execute(
            select(User).where(User.email == payload.email.lower())
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        role_result = await self._db.execute(
            select(Role).where(Role.name == payload.role_name)
        )
        role = role_result.scalar_one_or_none()
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role '{payload.role_name}' does not exist.",
            )

        user = User(
            email=payload.email.lower(),
            full_name=payload.full_name,
            department=payload.department.lower(),
            hashed_password=hash_password(payload.password),
            role_id=role.id,
        )
        self._db.add(user)
        await self._db.flush()
        log.info("auth.signup", user_id=user.id, role=payload.role_name)
        return user

    async def login(self, payload: LoginRequest) -> TokenResponse:
        result = await self._db.execute(
            select(User).where(User.email == payload.email.lower())
        )
        user = result.scalar_one_or_none()

        dummy_hash = "$2b$12$LCGLuI7y/ot7QNshVOdRiuEAkeFdFn8TtFTMOsaqP3reWAHvJdRvi"
        stored = user.hashed_password if user else dummy_hash
        password_ok = verify_password(payload.password, stored)

        if not user or not password_ok:
            log.warning("auth.login_failed", email=payload.email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated.",
            )

        role_result = await self._db.execute(
            select(Role).where(Role.id == user.role_id)
        )
        role = role_result.scalar_one()

        access = create_access_token(
            user_id=user.id,
            role=role.name,
            role_level=role.level,
            department=user.department,
        )
        refresh = create_refresh_token(user_id=user.id)

        from jose import jwt as jose_jwt
        raw = jose_jwt.decode(
            refresh,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
        self._db.add(
            RefreshToken(
                jti=raw["jti"],
                user_id=user.id,
                expires_at=datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days),
            )
        )

        user.last_login_at = datetime.utcnow()
        self._db.add(user)
        log.info("auth.login_success", user_id=user.id, role=role.name)

        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        try:
            raw = decode_refresh_token(refresh_token)
        except TokenExpiredError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired. Please log in again.",
            )
        except TokenInvalidError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
            )

        stored_result = await self._db.execute(
            select(RefreshToken).where(RefreshToken.jti == raw["jti"])
        )
        stored = stored_result.scalar_one_or_none()

        if stored is None or stored.revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is invalid or has been revoked.",
            )

        stored.revoked = True
        stored.revoked_at = datetime.utcnow()
        self._db.add(stored)

        user_result = await self._db.execute(
            select(User).where(User.id == raw["sub"])
        )
        user = user_result.scalar_one()
        role_result = await self._db.execute(
            select(Role).where(Role.id == user.role_id)
        )
        role = role_result.scalar_one()

        access = create_access_token(
            user_id=user.id,
            role=role.name,
            role_level=role.level,
            department=user.department,
        )
        new_refresh = create_refresh_token(user_id=user.id)

        from jose import jwt as jose_jwt
        new_raw = jose_jwt.decode(
            new_refresh,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
        self._db.add(
            RefreshToken(
                jti=new_raw["jti"],
                user_id=user.id,
                expires_at=datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days),
            )
        )

        return TokenResponse(
            access_token=access,
            refresh_token=new_refresh,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def logout(self, refresh_token: str) -> None:
        try:
            raw = decode_refresh_token(refresh_token)
        except (TokenExpiredError, TokenInvalidError):
            return

        stored_result = await self._db.execute(
            select(RefreshToken).where(RefreshToken.jti == raw["jti"])
        )
        stored = stored_result.scalar_one_or_none()
        if stored and not stored.revoked:
            stored.revoked = True
            stored.revoked_at = datetime.utcnow()
            self._db.add(stored)