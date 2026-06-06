from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Signup ────────────────────────────────────────────────────────────────────


class SignupRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    department: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=128)
    role_name: str = Field(default="employee", pattern=r"^(employee|manager|admin)$")

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        errors: list[str] = []
        if not any(c.isupper() for c in v):
            errors.append("at least one uppercase letter")
        if not any(c.islower() for c in v):
            errors.append("at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            errors.append("at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in v):
            errors.append("at least one special character")
        if errors:
            raise ValueError(f"Password must contain: {', '.join(errors)}")
        return v


class SignupResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    department: str
    created_at: datetime


# ── Login ─────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


# ── Refresh ───────────────────────────────────────────────────────────────────


class RefreshRequest(BaseModel):
    refresh_token: str


# ── User profile ──────────────────────────────────────────────────────────────


class UserProfile(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    role_level: int
    department: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
