"""Embedding service — wraps a sentence-transformer model for vector search."""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
_model = None


def _get_model():
    """Lazy-load the sentence-transformer so import time stays fast."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Return (N, dim) float32 array of embeddings."""
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)


def embed_query(query: str) -> np.ndarray:
    """Return a single 1-D embedding vector for a query string."""
    return embed_texts([query])[0]


def embedding_dim() -> int:
    """Return the dimensionality of the loaded model."""
    return _get_model().get_sentence_embedding_dimension()
