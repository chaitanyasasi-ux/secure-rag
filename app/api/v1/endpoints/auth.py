

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlmodel import select

from app.core.dependencies import get_current_active_user
from app.core.rate_limit import limiter
from app.core.security import TokenPayload

from app.db.session import AsyncSession, get_db
from app.models.user import Role, User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    UserProfile,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _get_auth_service(db: Annotated[AsyncSession, Depends(get_db)]) -> AuthService:
    return AuthService(db)


# POST /auth/signup 


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def signup(
    request: Request,
    payload: SignupRequest,
    svc: Annotated[AuthService, Depends(_get_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SignupResponse:
    user = await svc.signup(payload)
    role_result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = role_result.scalar_one()
    return SignupResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=role.name,
        department=user.department,
        created_at=user.created_at,
    )

# POST /auth/login 


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    svc: Annotated[AuthService, Depends(_get_auth_service)],
) -> TokenResponse:
    return await svc.login(payload)


#  POST /auth/refresh 


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and issue new access token",
)
async def refresh(
    body: RefreshRequest,
    svc: Annotated[AuthService, Depends(_get_auth_service)],
) -> TokenResponse:
    return await svc.refresh_tokens(body.refresh_token)


# POST /auth/logout 


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Revoke refresh token",
)
async def logout(
    body: RefreshRequest,
    svc: Annotated[AuthService, Depends(_get_auth_service)],
) -> dict:
    await svc.logout(body.refresh_token)
    return {"detail":"Successfully logged out"}


#GET /auth/me


@router.get(
    "/me",
    response_model=UserProfile,
    summary="Return the authenticated user's profile",
)
async def me(
    payload: Annotated[TokenPayload, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserProfile:
    from sqlmodel import select

    user_result = await db.execute(select(User).where(User.id == payload.user_id))
    user = user_result.scalar_one()


    return UserProfile(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=payload.role,
        role_level=payload.role_level,
        department=user.department,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )
