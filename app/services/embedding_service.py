from __future__ import annotations

import structlog
from fastembed import TextEmbedding

log = structlog.get_logger(__name__)

_model: TextEmbedding | None = None


def get_embedding_model() -> TextEmbedding:
    global _model
    if _model is None:
        log.info("embedding.loading_model", model="BAAI/bge-small-en-v1.5")
        _model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        log.info("embedding.model_loaded")
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    embeddings = list(model.embed(texts))
    return [e.tolist() for e in embeddings]


def embed_single(text: str) -> list[float]:
    return embed_texts([text])[0]