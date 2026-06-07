from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from fastapi import HTTPException, status
from sqlmodel import select

from app.core.config import get_settings
from app.core.hashing import hash_password, verify_password
from app.core.security import (
    TokenExpiredError,
    TokenInvalidError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.db.session import AsyncSession
from app.models.user import RefreshToken, Role, User
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse

log = structlog.get_logger(__name__)
settings = get_settings()


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Signup ────────────────────────────────────────────────────────────────

    async def signup(self, payload: SignupRequest) -> User:
        # Reject duplicate emails
        existing = await self._db.execute(
            select(User).where(User.email == payload.email.lower())
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        # Resolve role
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
        await self._db.flush()  # get the generated ID before commit

        log.info("auth.signup", user_id=user.id, role=payload.role_name)
        return user

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(self, payload: LoginRequest) -> TokenResponse:
        user_result = await self._db.execute(
            select(User).where(User.email == payload.email.lower())
        )
        user = user_result.first()

        # Constant-time comparison — always run verify_password even on miss
        # to prevent timing-based user enumeration
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

        # Load role for level info
        role_result = await self._db.execute(select(Role).where(Role.id == user.role_id))
        role = role_result.scalar_one()

        access = create_access_token(
            user_id=user.id,
            role=role.name,
            role_level=role.level,
            department=user.department,
        )
        refresh = create_refresh_token(user_id=user.id)

        # Persist refresh token JTI for revocation support
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
                expires_at=datetime.fromtimestamp(raw["exp"], tz=timezone.utc),
            )
        )

        # Update last login timestamp
        user.last_login_at = datetime.now(timezone.utc)
        self._db.add(user)

        log.info("auth.login_success", user_id=user.id, role=role.name)

        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    # ── Refresh ───────────────────────────────────────────────────────────────

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

        # Verify the token is in the DB and not revoked
        stored_result = await self._db.execute(
            select(RefreshToken).where(RefreshToken.jti == raw["jti"])
        )
        stored = stored_result.first()

        if stored is None or stored.revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is invalid or has been revoked.",
            )

        # Rotate: revoke old token and issue new pair
        stored.revoked = True
        stored.revoked_at = datetime.now(timezone.utc)
        self._db.add(stored)

        user_result = await self._db.execute(
            select(User).where(User.id == raw["sub"])
        )
        user = user_result.scalar_one()
        role_result = await self._db.execute(select(Role).where(Role.id == user.role_id))
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
                expires_at=datetime.fromtimestamp(new_raw["exp"], tz=timezone.utc),
            )
        )

        return TokenResponse(
            access_token=access,
            refresh_token=new_refresh,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    # ── Logout ────────────────────────────────────────────────────────────────

    async def logout(self, refresh_token: str) -> None:
        try:
            raw = decode_refresh_token(refresh_token)
        except (TokenExpiredError, TokenInvalidError):
            return  # Silently succeed — token is already invalid

        stored_result = await self._db.execute(
            select(RefreshToken).where(RefreshToken.jti == raw["jti"])
        )
        stored = stored_result.first()
        if stored and not stored.revoked:
            stored.revoked = True
            stored.revoked_at = datetime.now(timezone.utc)
            self._db.add(stored)
