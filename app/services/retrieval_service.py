from __future__ import annotations

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, Range

from app.core.config import get_settings
from app.schemas.query import RetrievedChunk
from app.services.embedding_service import embed_single

log = structlog.get_logger(__name__)
settings = get_settings()


def retrieve_chunks(
    client: QdrantClient,
    question: str,
    user_role_level: int,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """
    Convert question to vector, apply RBAC filter, return authorized chunks.

    The security guarantee:
    Qdrant only returns chunks where required_role_level <= user_role_level.
    Unauthorized chunks are never retrieved — not filtered after the fact.
    """

    # Step 1 — convert question to vector
    query_vector = embed_single(question)

    log.info(
        "retrieval.query_start",
        user_role_level=user_role_level,
        question_preview=question[:50],
    )

    # Step 2 — build the RBAC filter
    # This is the security gate — happens inside Qdrant before results return
    rbac_filter = Filter(
        must=[
            FieldCondition(
                key="required_role_level",
                range=Range(lte=user_role_level),
            )
        ]
    )

    # Step 3 — search Qdrant with vector + filter
    results = client.search(
        collection_name=settings.qdrant_collection_name,
        query_vector=query_vector,
        query_filter=rbac_filter,
        limit=limit,
        with_payload=True,
    )

    log.info(
        "retrieval.query_complete",
        results_count=len(results),
        user_role_level=user_role_level,
    )

    # Step 4 — convert Qdrant results to our schema
    chunks = []
    for result in results:
        payload = result.payload or {}
        chunk = RetrievedChunk(
            chunk_id=str(result.id),
            text=payload.get("text", ""),
            document_id=payload.get("document_id", ""),
            required_role_level=payload.get("required_role_level", 0),
            department=payload.get("department", ""),
            source_file=payload.get("source_file", ""),
            chunk_index=payload.get("chunk_index", 0),
            similarity_score=round(result.score, 4),
        )
        chunks.append(chunk)

    return chunks