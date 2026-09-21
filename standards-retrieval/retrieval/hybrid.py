from collections import defaultdict
from typing import List, Tuple, Dict, Optional

from indexing.embed_index import dense_search
from indexing.bm25_index import bm25_search

# Configurable constants for Reciprocal Rank Fusion
DEFAULT_RRF_K: int = 60

# How many candidates each retriever contributes before fusion.
#
# This was 30, chosen when the whole corpus was 30 standards — every document
# was a candidate, so recall was guaranteed. At a few thousand standards a
# fixed pool of 30 is a recall ceiling: if the right standard is not in the
# first 30 dense *or* the first 30 BM25 hits, no amount of re-ranking can
# recover it.
#
# The pool now grows with the corpus and is capped, because the cross-encoder
# re-ranks every candidate and its cost is linear in pool size.
_MIN_CANDIDATE_POOL: int = 30
_MAX_CANDIDATE_POOL: int = 120


def default_candidate_pool() -> int:
    """Candidate pool sized for the corpus actually loaded."""
    try:
        from data_loader import load_corpus

        corpus_size = len(load_corpus())
    except Exception:
        return _MIN_CANDIDATE_POOL

    # Roughly the square root of the corpus, which keeps the pool a shrinking
    # *fraction* of the corpus while still growing in absolute terms.
    scaled = int(corpus_size ** 0.5) * 3
    return max(_MIN_CANDIDATE_POOL, min(_MAX_CANDIDATE_POOL, scaled))


# Kept for callers that import it directly; prefer default_candidate_pool().
DEFAULT_CANDIDATE_POOL: int = 30


def rrf_merge(
    dense_results: List[Tuple[str, float]],
    bm25_results: List[Tuple[str, float]],
    k: int = DEFAULT_RRF_K,
    top_k: int = 20
) -> List[Tuple[str, float]]:
    """Merges dense and sparse search rankings using Reciprocal Rank Fusion (RRF).
    
    Formula:
        RRF_Score(d) = sum(1.0 / (k + rank_i(d))) for each system i where d appears.
        
    RRF handles disparate score scales (e.g. bounded cosine similarity [0, 1] vs 
    unbounded BM25 scores) without requiring arbitrary score normalization or calibration.
    
    Args:
        dense_results: List of (standard_id, cosine_score) sorted descending.
        bm25_results: List of (standard_id, raw_bm25_score) sorted descending.
        k: Smoothing constant (default=60) that penalizes lower-ranked documents.
        top_k: Maximum number of merged results to return.
        
    Returns:
        List of (standard_id, rrf_score) sorted descending by fused score.
    """
    scores: Dict[str, float] = defaultdict(float)

    # 1. Accumulate RRF scores from Dense FAISS ranking (1-indexed rank)
    for rank, (doc_id, _) in enumerate(dense_results, start=1):
        scores[doc_id] += 1.0 / (k + rank)

    # 2. Accumulate RRF scores from Sparse BM25 ranking (1-indexed rank)
    for rank, (doc_id, _) in enumerate(bm25_results, start=1):
        scores[doc_id] += 1.0 / (k + rank)

    # 3. Sort union of all scored documents descending by RRF score
    sorted_items = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    return sorted_items[:top_k]


def hybrid_search(
    query: str,
    top_k: int = 20,
    candidate_pool: Optional[int] = None,
    rrf_k: int = DEFAULT_RRF_K
) -> List[Tuple[str, float]]:
    """Executes hybrid retrieval combining dense semantic search and sparse lexical search.
    
    1. Fetches candidate_pool nearest neighbors via dense FAISS search.
    2. Fetches candidate_pool top documents via sparse BM25 search.
    3. Fuses rankings using Reciprocal Rank Fusion (RRF) with parameter rrf_k.
    4. Truncates and returns the top_k fused results.
    
    Args:
        query: Raw natural language query or procurement specification text.
        top_k: Number of final ranked standards to return.
        candidate_pool: Number of candidates to retrieve from each retriever before fusion.
        rrf_k: RRF smoothing constant (default=60).
        
    Returns:
        List of (standard_id, rrf_score) sorted descending by relevance.
    """
    if not query or not query.strip():
        return []

    # Sized from the corpus unless a caller pins it explicitly.
    if candidate_pool is None:
        candidate_pool = default_candidate_pool()

    dense_candidates = dense_search(query, top_k=candidate_pool)
    bm25_candidates = bm25_search(query, top_k=candidate_pool)

    return rrf_merge(
        dense_results=dense_candidates,
        bm25_results=bm25_candidates,
        k=rrf_k,
        top_k=top_k
    )
