from __future__ import annotations
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="The question to ask the system",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of chunks to retrieve",
    )


class RetrievedChunk(BaseModel):
    chunk_id: str
    text: str
    document_id: str
    required_role_level: int
    department: str
    source_file: str
    chunk_index: int
    similarity_score: float


class QueryResponse(BaseModel):
    question: str
    retrieved_chunks: list[RetrievedChunk]
    total_found: int
    user_role_level: int


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[str]
    user_role_level: int
    chunks_used: int