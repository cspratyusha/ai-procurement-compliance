import os
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ingestion import (
    BatchIngestRequest,
    IngestionResponse,
    IngestionStatsResponse
)
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/ingest", tags=["Data Ingestion"])

@router.post("/batch", response_model=IngestionResponse, summary="Ingest Batch of Standards & Metadata")
def ingest_batch(
    batch: BatchIngestRequest,
    db: Session = Depends(get_db)
):
    """
    Ingest product categories, Indian Standards metadata, cross-references,
    amendments, and certification rules across all four storage layers
    (PostgreSQL, Neo4j, Vector DB, BM25 Index).
    """
    try:
        response = IngestionService.ingest_batch(db=db, batch=batch)
        return response
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data Ingestion failed: {str(e)}"
        )

@router.post("/seed", response_model=IngestionResponse, summary="Seed Standards Data from File")
def seed_standards_data(db: Session = Depends(get_db)):
    """
    Seeds the system with curated BIS standards data across 4 core demo categories
    (Steel, PVC Pipes, Electrical Fittings, PPE Safety Equipment) from data/seed_standards.json.
    """
    seed_file_path = os.path.join(os.getcwd(), "data", "seed_standards.json")
    if not os.path.exists(seed_file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Seed dataset file not found at '{seed_file_path}'"
        )

    try:
        with open(seed_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        batch = BatchIngestRequest(**data)
        response = IngestionService.ingest_batch(db=db, batch=batch)
        return response
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to seed standards data: {str(e)}"
        )

@router.post("/rebuild-derived-stores", summary="Rebuild Neo4j, Vector DB & BM25 from PostgreSQL")
def rebuild_derived_stores(db: Session = Depends(get_db)):
    """
    Regenerates Neo4j Graph, Vector Database, and BM25 Sparse Index directly
    from PostgreSQL (Single Source of Truth) to resolve multi-store drift.
    """
    try:
        result = IngestionService.rebuild_derived_stores(db=db)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rebuild derived stores: {str(e)}"
        )

@router.get("/stats", response_model=IngestionStatsResponse, summary="Get Corpus Statistics Across Stores")
def get_ingestion_stats(db: Session = Depends(get_db)):
    """
    Returns total document/node/record counts across PostgreSQL, Neo4j,
    ChromaDB Vector Store, and BM25 Sparse Keyword Index.
    """
    try:
        return IngestionService.get_ingestion_stats(db=db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve stats: {str(e)}"
        )
