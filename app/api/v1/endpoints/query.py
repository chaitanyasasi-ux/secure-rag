

import time
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.dependencies import get_current_active_user
from app.core.rate_limit import limiter
from app.core.security import TokenPayload
from app.db.session import AsyncSession, get_db
from app.schemas.query import AskResponse, QueryRequest, QueryResponse
from app.services.audit_service import write_audit_log
from app.services.guardrail_service import GuardrailViolation, check_prompt
from app.services.llm_service import generate_answer
from app.services.qdrant_service import get_qdrant_client
from app.services.retrieval_service import retrieve_chunks

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/query", tags=["Query"])


@router.post(
    "",
    response_model=QueryResponse,
    summary="Retrieve relevant document chunks with RBAC filtering",
)
@limiter.limit("60/minute")
async def query_documents(
    request: Request,
    payload: QueryRequest,
    token: Annotated[TokenPayload, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> QueryResponse:
    start_time = time.monotonic()

    # Guardrail check
    try:
        check_prompt(payload.question)
    except GuardrailViolation as e:
        execution_ms = int((time.monotonic() - start_time) * 1000)
        await write_audit_log(
            db=db,
            user_id=token.user_id,
            user_role_level=token.role_level,
            question=payload.question,
            retrieved_chunk_ids=[],
            answer="BLOCKED BY GUARDRAIL",
            execution_ms=execution_ms,
            tokens_used=0,
            guardrail_blocked=True,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e.reason),
        )

    # RBAC retrieval
    client = get_qdrant_client()
    try:
        chunks = retrieve_chunks(
            client=client,
            question=payload.question,
            user_role_level=token.role_level,
            limit=payload.limit,
        )
    finally:
        client.close()

    execution_ms = int((time.monotonic() - start_time) * 1000)

    await write_audit_log(
        db=db,
        user_id=token.user_id,
        user_role_level=token.role_level,
        question=payload.question,
        retrieved_chunk_ids=[c.chunk_id for c in chunks],
        answer="retrieval_only",
        execution_ms=execution_ms,
        tokens_used=0,
        guardrail_blocked=False,
    )

    return QueryResponse(
        question=payload.question,
        retrieved_chunks=chunks,
        total_found=len(chunks),
        user_role_level=token.role_level,
    )


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a question and get an AI-generated answer",
    description=(
        "Full RAG pipeline: guardrail check → RBAC retrieval → "
        "Groq answer generation. Every query is audit logged."
    ),
)
@limiter.limit("30/minute")
async def ask_question(
    request: Request,
    payload: QueryRequest,
    token: Annotated[TokenPayload, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AskResponse:
    start_time = time.monotonic()

    # Step 1 — Guardrail
    try:
        check_prompt(payload.question)
    except GuardrailViolation as e:
        execution_ms = int((time.monotonic() - start_time) * 1000)
        await write_audit_log(
            db=db,
            user_id=token.user_id,
            user_role_level=token.role_level,
            question=payload.question,
            retrieved_chunk_ids=[],
            answer="BLOCKED BY GUARDRAIL",
            execution_ms=execution_ms,
            tokens_used=0,
            guardrail_blocked=True,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e.reason),
        )

    # Step 2 — RBAC retrieval
    client = get_qdrant_client()
    try:
        chunks = retrieve_chunks(
            client=client,
            question=payload.question,
            user_role_level=token.role_level,
            limit=payload.limit,
        )
    finally:
        client.close()

    # Step 3 — LLM generation
    answer = generate_answer(
        question=payload.question,
        chunks=chunks,
    )

    execution_ms = int((time.monotonic() - start_time) * 1000)

    # Step 4 — Audit log
    await write_audit_log(
        db=db,
        user_id=token.user_id,
        user_role_level=token.role_level,
        question=payload.question,
        retrieved_chunk_ids=[c.chunk_id for c in chunks],
        answer=answer,
        execution_ms=execution_ms,
        tokens_used=0,
        guardrail_blocked=False,
    )

    sources = list({chunk.document_id for chunk in chunks})

    log.info(
        "ask.completed",
        user_id=token.user_id,
        role_level=token.role_level,
        execution_ms=execution_ms,
        chunks_used=len(chunks),
    )

    return AskResponse(
        question=payload.question,
        answer=answer,
        sources=sources,
        user_role_level=token.role_level,
        chunks_used=len(chunks),
    )