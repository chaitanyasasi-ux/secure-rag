from __future__ import annotations

import time
from datetime import datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


async def write_audit_log(
    db: AsyncSession,
    user_id: str,
    user_role_level: int,
    question: str,
    retrieved_chunk_ids: list[str],
    answer: str,
    execution_ms: int,
    tokens_used: int,
    guardrail_blocked: bool,
) -> None:
    """
    Write an audit log entry to the database using raw SQL.

    Why raw SQL instead of SQLModel:
    - Bypasses the timezone-aware datetime issue we hit before
    - Bypasses SQLModel version conflicts
    - Audit logs must NEVER fail silently — raw SQL gives us full control
    - If the audit write fails, we log the error but don't crash the request

    The try/except here is intentional — a failed audit log should never
    cause the user's request to fail. But we log the failure so it can
    be investigated.
    """
    try:
        chunk_ids_str = ",".join(retrieved_chunk_ids)
        answer_preview = answer[:500] if answer else ""

        await db.execute(
            text("""
                INSERT INTO audit_logs (
                    user_id,
                    user_role_level,
                    question,
                    retrieved_chunk_ids,
                    answer_preview,
                    execution_ms,
                    tokens_used,
                    guardrail_passed,
                    guardrail_blocked,
                    created_at
                ) VALUES (
                    :user_id,
                    :user_role_level,
                    :question,
                    :retrieved_chunk_ids,
                    :answer_preview,
                    :execution_ms,
                    :tokens_used,
                    :guardrail_passed,
                    :guardrail_blocked,
                    :created_at
                )
            """),
            {
                "user_id": user_id,
                "user_role_level": user_role_level,
                "question": question[:1000],
                "retrieved_chunk_ids": chunk_ids_str,
                "answer_preview": answer_preview,
                "execution_ms": execution_ms,
                "tokens_used": tokens_used,
                "guardrail_passed": not guardrail_blocked,
                "guardrail_blocked": guardrail_blocked,
                "created_at": datetime.utcnow(),
            }
        )
        await db.commit()

        log.info(
            "audit.written",
            user_id=user_id,
            role_level=user_role_level,
            execution_ms=execution_ms,
            chunks_count=len(retrieved_chunk_ids),
            guardrail_blocked=guardrail_blocked,
        )

    except Exception as exc:
        log.error(
            "audit.write_failed",
            error=str(exc),
            user_id=user_id,
        )