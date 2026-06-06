from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: int = Field(default=None, primary_key=True)
    user_id: str = Field(max_length=36, index=True)
    user_role_level: int
    question: str = Field(max_length=1000)
    retrieved_chunk_ids: str = Field(
        default="",
        max_length=2000,
        description="Comma-separated list of retrieved chunk IDs",
    )
    answer_preview: str = Field(
        default="",
        max_length=500,
        description="First 500 characters of the AI answer",
    )
    execution_ms: int = Field(
        default=0,
        description="Total pipeline execution time in milliseconds",
    )
    tokens_used: int = Field(default=0)
    guardrail_passed: bool = Field(default=True)
    guardrail_blocked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)