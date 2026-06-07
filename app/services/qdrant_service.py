from __future__ import annotations

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    PayloadSchemaType,
    Range,
    ScoredPoint,
    VectorParams,
)

from app.core.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

VECTOR_SIZE = 384

def get_qdrant_client() -> QdrantClient:
    if settings.qdrant_api_key:
        return QdrantClient(
            url=f"https://{settings.qdrant_host}",
            api_key=settings.qdrant_api_key,
        )
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )

def setup_collection(client: QdrantClient) -> None:
    existing = client.get_collections()
    names = [c.name for c in existing.collections]

    if settings.qdrant_collection_name not in names:
        client.create_collection(
            collection_name=settings.qdrant_collection_name,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
        log.info("qdrant.collection_created", name=settings.qdrant_collection_name)

        client.create_payload_index(
            collection_name=settings.qdrant_collection_name,
            field_name="required_role_level",
            field_schema=PayloadSchemaType.INTEGER,
        )

        client.create_payload_index(
            collection_name=settings.qdrant_collection_name,
            field_name="department",
            field_schema=PayloadSchemaType.KEYWORD,
        )

        log.info("qdrant.indexes_created")
    else:
        log.info("qdrant.collection_exists", name=settings.qdrant_collection_name)


def search_chunks(
    client: QdrantClient,
    query_vector: list[float],
    user_role_level: int,
    limit: int = 5,
    department: str | None = None,
) -> list[ScoredPoint]:
    must_conditions = [
        FieldCondition(
            key="required_role_level",
            range=Range(lte=user_role_level),
        )
    ]

    if department and department != "all":
        must_conditions.append(
            FieldCondition(
                key="department",
                match=MatchValue(value=department),
            )
        )

    results = client.search(
        collection_name=settings.qdrant_collection_name,
        query_vector=query_vector,
        query_filter=Filter(must=must_conditions),
        limit=limit,
        with_payload=True,
    )

    log.info(
        "qdrant.search_completed",
        results_count=len(results),
        user_role_level=user_role_level,
    )

    return results