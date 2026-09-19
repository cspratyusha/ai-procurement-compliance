import time
from typing import List, Tuple, Dict, Optional, Union, Any
from sentence_transformers import CrossEncoder

from data.models import Standard
from data_loader import load_corpus, get_standard_by_id
from indexing.embed_index import get_standard_embedding_text
from retrieval.hybrid import hybrid_search
from retrieval.postprocess import apply_supersession_penalty

_RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_CROSS_ENCODER_INSTANCE: Optional[CrossEncoder] = None


def get_cross_encoder_model() -> CrossEncoder:
    """Loads and caches the CrossEncoder singleton instance.
    
    Uses 'cross-encoder/ms-marco-MiniLM-L-6-v2' (CPU-runnable, 6-layer MiniLM).
    Cached globally so load time is incurred only once per process.
    """
    global _CROSS_ENCODER_INSTANCE
    if _CROSS_ENCODER_INSTANCE is None:
        print(f"[ReRanking] Loading cross-encoder model '{_RERANKER_MODEL_NAME}'...")
        _CROSS_ENCODER_INSTANCE = CrossEncoder(_RERANKER_MODEL_NAME)
    return _CROSS_ENCODER_INSTANCE


def rerank(
    query: str,
    candidate_ids: List[str],
    corpus: Optional[Dict[str, Standard]] = None,
    top_k: int = 10
) -> List[Tuple[str, float]]:
    """Re-scores a narrowed candidate set of standards using joint query-document cross-attention.
    
    1. Reconstructs text pairs: (query, get_standard_embedding_text(std)).
    2. Runs batched prediction via CrossEncoder for fast CPU inference.
    3. Sorts candidate standards descending by raw cross-encoder logit scores.
    4. Returns top_k (standard_id, cross_encoder_score) tuples.
    
    Args:
        query: User procurement query or specification text.
        candidate_ids: Candidate standard IDs from Stage B retrieval (e.g. top-20 from hybrid_search).
        corpus: Optional dictionary of ID -> Standard. If None, loaded from in-memory cache.
        top_k: Maximum number of re-ranked results to return.
        
    Returns:
        List of (standard_id, cross_encoder_score) sorted descending by relevance.
    """
    if not query or not query.strip() or not candidate_ids:
        return []

    if corpus is None:
        # Fetch cached standards
        all_standards = load_corpus()
        corpus = {std.id: std for std in all_standards}

    valid_candidates = []
    pairs = []
    q_text = query.strip()

    for cid in candidate_ids:
        std = corpus.get(cid)
        if std:
            valid_candidates.append(cid)
            doc_text = get_standard_embedding_text(std)
            pairs.append((q_text, doc_text))

    if not pairs:
        return []

    model = get_cross_encoder_model()
    # Batch predict all candidate pairs in a single inference call
    scores = model.predict(pairs, batch_size=32, show_progress_bar=False)

    scored_results = [(cid, float(score)) for cid, score in zip(valid_candidates, scores)]
    scored_results.sort(key=lambda x: x[1], reverse=True)

    return scored_results[:top_k]


def full_retrieve(
    query: str,
    top_k: int = 10,
    candidate_pool_k: int = 20,
    debug: bool = False,
    return_metadata: bool = False
) -> Union[List[Tuple[str, float]], Tuple[List[Tuple[str, float]], List[Dict[str, Any]]]]:
    """Full End-to-End Retrieval & Re-ranking pipeline (Stage B + Stage D).
    
    Chains:
      1. hybrid_search(query, top_k=candidate_pool_k) -> candidates via FAISS + BM25 RRF
      2. rerank(query, candidate_ids, top_k=candidate_pool_k) -> precision cross-encoder re-ranking
      3. apply_supersession_penalty(...) -> floored active vs superseded resolution
      
    Args:
        query: User procurement specification or question.
        top_k: Number of final top standards to return.
        candidate_pool_k: Number of candidates retrieved in the first-stage hybrid pass.
        debug: If True, prints candidate re-ordering transformation for verification.
        return_metadata: If True, returns (ranked_results, nearby_superseded).
        
    Returns:
        List of (standard_id, cross_encoder_score) sorted descending, or tuple with nearby_superseded.
    """
    if not query or not query.strip():
        return ([], []) if return_metadata else []

    # First-stage hybrid retrieval
    hybrid_candidates = hybrid_search(query, top_k=candidate_pool_k)
    candidate_ids = [cid for cid, _ in hybrid_candidates]

    # Second-stage cross-encoder re-ranking over full candidate pool
    reranked = rerank(query=query, candidate_ids=candidate_ids, top_k=candidate_pool_k)
    
    if return_metadata:
        penalized, nearby = apply_supersession_penalty(
            reranked, penalty=2.0, top_k=top_k, return_metadata=True
        )
        return penalized[:top_k], nearby
    else:
        penalized = apply_supersession_penalty(
            reranked, penalty=2.0, top_k=top_k, return_metadata=False
        )
        return penalized[:top_k]
