
from typing import Annotated
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from app.core.dependencies import require_role
from app.core.roles import RoleLevel
from app.core.security import TokenPayload
from app.db.session import AsyncSession, get_db

router = APIRouter(prefix="/audit", tags=["Audit"])


class AuditEntry(BaseModel):
    id: int
    user_id: str
    user_role_level: int
    question: str
    retrieved_chunk_ids: str
    answer_preview: str
    execution_ms: int
    tokens_used: int
    guardrail_blocked: bool
    created_at: str


@router.get(
    "/logs",
    response_model=list[AuditEntry],
    summary="View audit logs — Admin only",
    description="Returns the 50 most recent audit log entries. Requires Admin role.",
)
async def get_audit_logs(
    token: Annotated[TokenPayload, Depends(require_role(RoleLevel.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AuditEntry]:
    result = await db.execute(
        text("""
            SELECT
                id, user_id, user_role_level, question,
                retrieved_chunk_ids, answer_preview,
                execution_ms, tokens_used,
                guardrail_blocked, created_at
            FROM audit_logs
            ORDER BY created_at DESC
            LIMIT 50
        """)
    )
    rows = result.fetchall()

    return [
        AuditEntry(
            id=row.id,
            user_id=row.user_id,
            user_role_level=row.user_role_level,
            question=row.question,
            retrieved_chunk_ids=row.retrieved_chunk_ids,
            answer_preview=row.answer_preview,
            execution_ms=row.execution_ms,
            tokens_used=row.tokens_used,
            guardrail_blocked=row.guardrail_blocked,
            created_at=str(row.created_at),
        )
        for row in rows
    ]