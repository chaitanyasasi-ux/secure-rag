from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.core.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

# ── Engine ────────────────────────────────────────────────────────────────────

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=not settings.is_production,  # SQL logging disabled in prod
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,               # validates connections before checkout
    pool_recycle=3600,                # recycle connections after 1 h
)

AsyncSessionLocal: sessionmaker = sessionmaker(  # type: ignore[call-overload]
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ── Session dependency ────────────────────────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session and guarantees
    rollback on exception + close on exit.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Schema initialisation (dev / test only) ───────────────────────────────────


async def init_db() -> None:
    async with engine.begin() as conn:
        from app.models.user import Permission, Role, RolePermission, User, RefreshToken
        from app.models.audit import AuditLog
        await conn.run_sync(SQLModel.metadata.create_all)
    await _seed_roles()
    log.info("database.initialised")


async def _seed_roles() -> None:
    """Insert default roles if they don't already exist."""
    from sqlalchemy import text
    from datetime import datetime
    from app.models.user import Role
    import uuid

    default_roles = [
        {"name": "employee", "level": 1, "description": "Standard employee access"},
        {"name": "manager", "level": 2, "description": "Manager-level document access"},
        {"name": "admin", "level": 3, "description": "Full system access"},
    ]

    async with AsyncSessionLocal() as session:
        for role_data in default_roles:
            result = await session.execute(
                text("SELECT id FROM roles WHERE name = :name"),
                {"name": role_data["name"]}
            )
            if result.first() is None:
                await session.execute(
                    text(
                        "INSERT INTO roles (id, name, level, description, created_at) "
                        "VALUES (:id, :name, :level, :description, :created_at)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "name": role_data["name"],
                        "level": role_data["level"],
                        "description": role_data["description"],
                        "created_at": datetime.utcnow(),
                    }
                )
        await session.commit()

    log.info("database.roles_seeded")
