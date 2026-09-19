"""Retrieval module for hybrid search, fusion, and cross-encoder re-ranking."""
from retrieval.hybrid import hybrid_search, rrf_merge, DEFAULT_RRF_K, DEFAULT_CANDIDATE_POOL
from retrieval.rerank import rerank, full_retrieve, get_cross_encoder_model

__all__ = [
    "hybrid_search",
    "rrf_merge",
    "DEFAULT_RRF_K",
    "DEFAULT_CANDIDATE_POOL",
    "rerank",
    "full_retrieve",
    "get_cross_encoder_model",
]
