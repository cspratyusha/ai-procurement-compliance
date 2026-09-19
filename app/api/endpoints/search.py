import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["AI Search & Retrieval"])


@router.get("/vector", summary="Dense Vector Semantic Search")
def vector_search(
    q: str = Query(..., min_length=2, description="Natural language procurement requirement or query"),
    category_id: Optional[str] = Query(None, description="Optional filter by product category ID"),
    limit: int = Query(10, ge=1, le=50, description="Max candidate standards to retrieve"),
    db: Session = Depends(get_db),
):
    """
    **Stage 1 Dense Semantic Search**:
    Uses SentenceTransformer embeddings to query ChromaDB HNSW cosine vector index.
    Returns semantically matched standards even if keywords differ.
    """
    return RetrievalService.vector_search(
        query=q,
        top_k=limit,
        category_id=category_id,
        db=db,
    )


@router.get("/keyword", summary="Sparse BM25 Keyword Search")
def keyword_search(
    q: str = Query(..., min_length=2, description="Exact technical terms or IS standard numbers"),
    limit: int = Query(10, ge=1, le=50, description="Max candidate standards to retrieve"),
    db: Session = Depends(get_db),
):
    """
    **Stage 1 Sparse Search**:
    Uses BM25Okapi inverted index over standard numbers, titles, and scopes.
    Excels at exact technical term, material grade, and partial IS-number matching.
    """
    return RetrievalService.keyword_search(
        query=q,
        top_k=limit,
        db=db,
    )


@router.get("/hybrid", summary="Hybrid Search (Dense Vector + BM25 Fusion)")
def hybrid_search(
    q: str = Query(..., min_length=2, description="Search query"),
    category_id: Optional[str] = Query(None, description="Filter by product category"),
    dense_weight: float = Query(0.6, ge=0.0, le=1.0, description="Weight for dense semantic score"),
    sparse_weight: float = Query(0.4, ge=0.0, le=1.0, description="Weight for sparse BM25 score"),
    limit: int = Query(10, ge=1, le=50, description="Number of results to return"),
    db: Session = Depends(get_db),
):
    """
    **Stage 1 & 2 Hybrid AI Retrieval Engine**:
    Fuses Dense Vector Search and BM25 Sparse Search to eliminate both false-negative modes.
    Enriched with live PostgreSQL metadata: active/superseded status, amendment counts, and certification rules.
    """
    return RetrievalService.hybrid_search(
        query=q,
        top_k=limit,
        category_id=category_id,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
        db=db,
    )
