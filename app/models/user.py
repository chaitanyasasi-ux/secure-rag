"""
Database models.  SQLModel gives us a single source of truth for both
the ORM table definition and the Pydantic schema.

Table hierarchy:
    roles  ──<  user_roles  >──  users
    roles  ──<  role_permissions  >──  permissions
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, List

from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    return datetime.utcnow()

def _new_uuid() -> str:
    return str(uuid.uuid4())


class Role(SQLModel, table=True):
    __tablename__ = "roles"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    name: str = Field(unique=True, index=True, max_length=64)
    level: int = Field(ge=1)
    description: str = Field(default="", max_length=255)
    created_at: datetime = Field(default_factory=_utcnow)


class Permission(SQLModel, table=True):
    __tablename__ = "permissions"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    name: str = Field(unique=True, index=True, max_length=128)
    description: str = Field(default="", max_length=255)


class RolePermission(SQLModel, table=True):
    __tablename__ = "role_permissions"

    role_id: str = Field(foreign_key="roles.id", primary_key=True)
    permission_id: str = Field(foreign_key="permissions.id", primary_key=True)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=254)
    full_name: str = Field(max_length=255)
    department: str = Field(max_length=128)
    hashed_password: str = Field(max_length=255)
    role_id: str = Field(foreign_key="roles.id", index=True)
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    last_login_at: Optional[datetime] = Field(default=None)


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"

    jti: str = Field(primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", index=True)
    issued_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime
    revoked: bool = Field(default=False)
    revoked_at: Optional[datetime] = Field(default=None)