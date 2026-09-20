"""Hybrid retrieval engine — dense (pgvector) + sparse (BM25) + cross-encoder rerank."""

from __future__ import annotations

import logging
from typing import Any

from api.db import get_connection
from api.embeddings import embed_query
from api import bm25_search

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cross-encoder (lazy loaded)
# ---------------------------------------------------------------------------

_cross_encoder = None


def _get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        try:
            from sentence_transformers import CrossEncoder
            _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("Cross-encoder loaded successfully.")
        except Exception as e:
            logger.warning("Cross-encoder unavailable: %s. Skipping rerank.", e)
    return _cross_encoder


# ---------------------------------------------------------------------------
# Dense vector search via pgvector
# ---------------------------------------------------------------------------

def _dense_search(query: str, top_k: int = 20, category: str | None = None) -> list[dict]:
    """Semantic search using pgvector cosine distance."""
    vec = embed_query(query)
    vec_literal = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"

    where = "WHERE embedding IS NOT NULL"
    params: list[Any] = [vec_literal]
    if category:
        where += " AND category = %s"
        params.append(category)
    params.append(top_k)

    sql = f"""
        SELECT id, number, title, scope, description, category,
               version, last_amended, status, keywords_json,
               1 - (embedding <=> %s::vector) AS dense_score
        FROM standards
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    # Need vec_literal twice — once for score, once for ORDER BY
    params_full = [vec_literal] + params[1:]  # category?, top_k
    params_full.insert(len(params_full) - 1, vec_literal)

    # Simpler: just build it explicitly
    if category:
        sql = """
            SELECT id, number, title, scope, description, category,
                   version, last_amended, status, keywords_json,
                   1 - (embedding <=> %s::vector) AS dense_score
            FROM standards
            WHERE embedding IS NOT NULL AND category = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        final_params = [vec_literal, category, vec_literal, top_k]
    else:
        sql = """
            SELECT id, number, title, scope, description, category,
                   version, last_amended, status, keywords_json,
                   1 - (embedding <=> %s::vector) AS dense_score
            FROM standards
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        final_params = [vec_literal, vec_literal, top_k]

    with get_connection() as conn:
        rows = conn.execute(sql, final_params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Hybrid search: merge dense + sparse, then optionally cross-encode
# ---------------------------------------------------------------------------

def hybrid_search(
    query: str,
    top_k: int = 10,
    category: str | None = None,
    dense_weight: float = 0.6,
    sparse_weight: float = 0.4,
    use_rerank: bool = True,
) -> list[dict]:
    """
    Hybrid retrieval pipeline:
      1. Dense search (pgvector cosine similarity)
      2. Sparse search (BM25)
      3. Score fusion (weighted combination)
      4. Cross-encoder rerank (optional)
    """
    # --- Step 1: Dense candidates ---
    dense_results = _dense_search(query, top_k=top_k * 2, category=category)
    dense_map: dict[str, dict] = {}
    dense_scores: dict[str, float] = {}
    for r in dense_results:
        dense_map[r["id"]] = r
        dense_scores[r["id"]] = float(r.get("dense_score", 0))

    # Normalise dense scores to [0, 1]
    max_dense = max(dense_scores.values()) if dense_scores else 1.0
    if max_dense > 0:
        for k in dense_scores:
            dense_scores[k] /= max_dense

    # --- Step 2: Sparse candidates ---
    sparse_hits = bm25_search.search(query, top_k=top_k * 2)
    sparse_scores: dict[str, float] = {}
    max_sparse = sparse_hits[0][1] if sparse_hits else 1.0
    for sid, score in sparse_hits:
        sparse_scores[sid] = score / max_sparse if max_sparse > 0 else 0

    # --- Step 3: Merge and fuse scores ---
    all_ids = set(dense_scores.keys()) | set(sparse_scores.keys())
    fused: list[tuple[str, float]] = []
    for sid in all_ids:
        d = dense_scores.get(sid, 0.0)
        s = sparse_scores.get(sid, 0.0)
        fused.append((sid, dense_weight * d + sparse_weight * s))
    fused.sort(key=lambda x: x[1], reverse=True)

    # Keep top candidates for reranking
    candidate_ids = [sid for sid, _ in fused[: top_k * 2]]

    # Fetch any rows we got from sparse but not dense
    missing_ids = [sid for sid in candidate_ids if sid not in dense_map]
    if missing_ids:
        placeholders = ",".join(["%s"] * len(missing_ids))
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT id, number, title, scope, description, category, "
                f"version, last_amended, status, keywords_json "
                f"FROM standards WHERE id IN ({placeholders})",
                missing_ids,
            ).fetchall()
        for r in rows:
            dense_map[r["id"]] = dict(r)

    # --- Step 4: Cross-encoder rerank ---
    candidates = []
    for sid in candidate_ids:
        if sid in dense_map:
            candidates.append(dense_map[sid])

    if use_rerank and len(candidates) > 1:
        ce = _get_cross_encoder()
        if ce is not None:
            pairs = [
                (query, f"{c['number']} {c['title']} {c['scope']}")
                for c in candidates
            ]
            try:
                ce_scores = ce.predict(pairs)
                for i, c in enumerate(candidates):
                    c["cross_encoder_score"] = float(ce_scores[i])
                candidates.sort(key=lambda x: x.get("cross_encoder_score", 0), reverse=True)
            except Exception as e:
                logger.warning("Cross-encoder rerank failed: %s", e)

    # Attach all scores
    for c in candidates:
        c["dense_score"] = dense_scores.get(c["id"], 0.0)
        c["bm25_score"] = sparse_scores.get(c["id"], 0.0)
        fused_map = dict(fused)
        c["hybrid_score"] = fused_map.get(c["id"], 0.0)

    return candidates[:top_k]
