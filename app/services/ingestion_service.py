from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.services.embedding_service import embed_texts
from app.core.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200


def chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def ingest_document(
    client: QdrantClient,
    text: str,
    document_id: str,
    required_role_level: int,
    department: str,
    source_file: str,
) -> int:
    chunks = chunk_text(text)
    total_chunks = len(chunks)

    log.info("ingestion.chunking_complete", document_id=document_id, total_chunks=total_chunks)

    vectors = embed_texts(chunks)

    log.info("ingestion.embeddings_generated", document_id=document_id, vectors_count=len(vectors))

    points = []
    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "text": chunk,
                "document_id": document_id,
                "required_role_level": required_role_level,
                "department": department,
                "source_file": source_file,
                "chunk_index": i,
                "total_chunks": total_chunks,
                "ingested_at": datetime.utcnow().isoformat(),
            },
        )
        points.append(point)

    client.upsert(
        collection_name=settings.qdrant_collection_name,
        points=points,
    )

    log.info(
        "ingestion.complete",
        document_id=document_id,
        chunks_stored=total_chunks,
        required_role_level=required_role_level,
    )

    return total_chunks