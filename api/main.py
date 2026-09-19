"""AI Procurement Compliance API.

Provides read access to the standards corpus, relationships,
certification rules, full-text search, semantic search, and hybrid
retrieval with cross-encoder reranking.
"""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, HTTPException, Query

from api.db import get_connection
from api.models import (
    Amendment,
    CertificationRule,
    HybridSearchResult,
    Relationship,
    SearchResult,
    SemanticSearchResult,
    Standard,
    StandardDetail,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Procurement Compliance",
    version="0.2.0",
    description="Query Indian Standards for procurement specifications — with semantic & hybrid AI search.",
)


# ---------------------------------------------------------------------------
# Startup — build BM25 index
# ---------------------------------------------------------------------------

@app.on_event("startup")
def _startup():
    """Build in-memory BM25 index on startup."""
    from api import bm25_search
    try:
        n = bm25_search.load_from_db(get_connection)
        logger.info("BM25 index built with %d standards.", n)
    except Exception as e:
        logger.warning("BM25 index build failed (DB may be empty): %s", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_keywords(row: dict) -> list[str]:
    """Normalise keywords_json (stored as JSONB) into a plain list."""
    kw = row.get("keywords_json", [])
    if isinstance(kw, str):
        kw = json.loads(kw)
    return kw


def _row_to_standard(row: dict) -> dict:
    """Map a DB row to the Standard schema fields."""
    return {
        "id": row["id"],
        "number": row["number"],
        "title": row["title"],
        "scope": row["scope"],
        "description": row["description"],
        "category": row["category"],
        "version": row["version"],
        "last_amended": row["last_amended"],
        "status": row["status"],
        "keywords": _parse_keywords(row),
    }


# ---------------------------------------------------------------------------
# Routes — Core CRUD
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check — confirms the database is reachable."""
    with get_connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/standards", response_model=list[Standard])
def list_standards(
    category: str | None = Query(default=None, description="Filter by category slug"),
    status: str | None = Query(default=None, description="Filter by status (active / superseded)"),
    limit: int = Query(default=50, ge=1, le=500),
):
    """List standards with optional category and status filters."""
    clauses: list[str] = []
    params: list[object] = []

    if category:
        clauses.append("category = %s")
        params.append(category)
    if status:
        clauses.append("status = %s")
        params.append(status)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    sql = f"""
        SELECT id, number, title, scope, description, category,
               version, last_amended, status, keywords_json
        FROM standards {where}
        ORDER BY number
        LIMIT %s
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_standard(r) for r in rows]


@app.get("/standards/search", response_model=list[SearchResult])
def search_standards(
    q: str = Query(min_length=2, description="Search terms"),
    category: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
):
    """Full-text search across number, title, scope and description."""
    clauses = [
        "to_tsvector('simple', number || ' ' || title || ' ' || scope || ' ' || description) "
        "@@ plainto_tsquery('simple', %s)"
    ]
    params: list[object] = [q]

    if category:
        clauses.append("category = %s")
        params.append(category)

    # ts_rank needs the query token repeated
    params.append(q)
    params.append(limit)

    sql = f"""
        SELECT id, number, title, scope, description, category,
               version, last_amended, status, keywords_json,
               ts_rank(
                   to_tsvector('simple', number || ' ' || title || ' ' || scope || ' ' || description),
                   plainto_tsquery('simple', %s)
               ) AS rank
        FROM standards
        WHERE {' AND '.join(clauses)}
        ORDER BY rank DESC, last_amended DESC
        LIMIT %s
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [{**_row_to_standard(r), "rank": float(r["rank"])} for r in rows]


# ---------------------------------------------------------------------------
# Routes — Semantic & Hybrid Search (AI Pipeline)
# ---------------------------------------------------------------------------

@app.get("/standards/semantic-search", response_model=list[SemanticSearchResult])
def semantic_search(
    q: str = Query(min_length=2, description="Natural language query"),
    category: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
):
    """Dense vector search using sentence-transformer embeddings via pgvector."""
    from api.embeddings import embed_query

    vec = embed_query(q)
    vec_literal = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"

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
        params = [vec_literal, category, vec_literal, limit]
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
        params = [vec_literal, vec_literal, limit]

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [{**_row_to_standard(r), "dense_score": float(r["dense_score"])} for r in rows]


@app.get("/standards/hybrid-search", response_model=list[HybridSearchResult])
def hybrid_search_endpoint(
    q: str = Query(min_length=2, description="Natural language query"),
    category: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    rerank: bool = Query(default=True, description="Apply cross-encoder reranking"),
):
    """Hybrid search: dense + BM25 fusion with optional cross-encoder rerank.

    This is the full AI retrieval pipeline from the architecture:
    1. Dense embedding search (pgvector)
    2. Sparse keyword search (BM25)
    3. Score fusion (weighted merge)
    4. Cross-encoder precision reranking
    """
    from api.retrieval import hybrid_search

    results = hybrid_search(
        query=q,
        top_k=limit,
        category=category,
        use_rerank=rerank,
    )
    return [
        {
            **_row_to_standard(r),
            "dense_score": r.get("dense_score", 0.0),
            "bm25_score": r.get("bm25_score", 0.0),
            "hybrid_score": r.get("hybrid_score", 0.0),
            "cross_encoder_score": r.get("cross_encoder_score"),
        }
        for r in results
    ]


# ---------------------------------------------------------------------------
# Routes — Detail, Categories, Relationships, Amendments, Certification
# ---------------------------------------------------------------------------

@app.get("/standards/{standard_id}", response_model=StandardDetail)
def get_standard(standard_id: str):
    """Fetch a single standard and all its relationships."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM standards WHERE id = %s", (standard_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, detail="Standard not found")

        rels = conn.execute(
            """
            SELECT source_id, target_id, type
            FROM standard_relationships
            WHERE source_id = %s OR target_id = %s
            """,
            (standard_id, standard_id),
        ).fetchall()

    return {
        **_row_to_standard(row),
        "relationships": [dict(r) for r in rels],
    }


@app.get("/categories", response_model=list[str])
def list_categories():
    """Return every distinct category in the corpus."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM standards ORDER BY category"
        ).fetchall()
    return [r["category"] for r in rows]


@app.get("/certification-rules", response_model=list[CertificationRule])
def list_certification_rules(
    category: str | None = Query(default=None, description="Filter by category slug"),
):
    """List BIS certification rules, optionally filtered by category."""
    if category:
        sql = "SELECT category, scheme_type, mandatory FROM certification_rules WHERE category = %s ORDER BY scheme_type"
        params: tuple = (category,)
    else:
        sql = "SELECT category, scheme_type, mandatory FROM certification_rules ORDER BY category, scheme_type"
        params = ()

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@app.get("/relationships", response_model=list[Relationship])
def list_relationships():
    """Return every relationship edge in the graph."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT source_id, target_id, type FROM standard_relationships ORDER BY source_id, target_id"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/standards/{standard_id}/amendments", response_model=list[Amendment])
def list_amendments(standard_id: str):
    """List amendments for a specific standard."""
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM standards WHERE id = %s", (standard_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail="Standard not found")
        rows = conn.execute(
            "SELECT amendment_id, standard_id, amendment_number, date_issued, change_summary "
            "FROM amendments WHERE standard_id = %s ORDER BY amendment_number",
            (standard_id,),
        ).fetchall()
    return [dict(r) for r in rows]
