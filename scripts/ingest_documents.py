"""
Document ingestion script.

Usage:
    python scripts/ingest_documents.py

This script loads all sample documents into Qdrant with their
security metadata. Run this once before testing the RAG pipeline.
"""
from __future__ import annotations

import asyncio
import sys
import os

# Add project root to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import structlog
from app.core.logging import configure_logging
from app.services.qdrant_service import get_qdrant_client, setup_collection
from app.services.ingestion_service import ingest_document

configure_logging()
log = structlog.get_logger(__name__)

# Documents to ingest with their security metadata
DOCUMENTS = [
    {
        "file": "sample_docs/employee_handbook.txt",
        "document_id": "employee-handbook",
        "required_role_level": 1,
        "department": "all",
    },
    {
        "file": "sample_docs/manager_guidelines.txt",
        "document_id": "manager-guidelines",
        "required_role_level": 2,
        "department": "all",
    },
    {
        "file": "sample_docs/board_strategy.txt",
        "document_id": "board-strategy",
        "required_role_level": 3,
        "department": "all",
    },
]


def main() -> None:
    log.info("ingestion.starting")

    client = get_qdrant_client()
    setup_collection(client)

    total_chunks = 0

    for doc in DOCUMENTS:
        file_path = doc["file"]

        if not os.path.exists(file_path):
            log.error("ingestion.file_not_found", file=file_path)
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        log.info(
            "ingestion.processing_file",
            file=file_path,
            required_role_level=doc["required_role_level"],
        )

        chunks_stored = ingest_document(
            client=client,
            text=text,
            document_id=doc["document_id"],
            required_role_level=doc["required_role_level"],
            department=doc["department"],
            source_file=file_path,
        )

        total_chunks += chunks_stored
        log.info(
            "ingestion.document_complete",
            document_id=doc["document_id"],
            chunks_stored=chunks_stored,
        )

    log.info("ingestion.all_complete", total_chunks=total_chunks)
    client.close()


if __name__ == "__main__":
    main()