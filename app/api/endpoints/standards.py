import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.postgres_models import StandardModel, ProductCategoryModel, CertificationRuleModel
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Standards & Categories"])


@router.get("/standards", summary="List Indian Standards with Filters")
def list_standards(
    category_id: Optional[str] = Query(None, description="Filter by product category ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (active / superseded / withdrawn)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve Indian Standards metadata from PostgreSQL with category and status filtering."""
    query = db.query(StandardModel)
    if category_id:
        query = query.filter(StandardModel.category_id == category_id)
    if status_filter:
        query = query.filter(StandardModel.status == status_filter)

    total = query.count()
    items = query.order_by(StandardModel.standard_number).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "standards": [
            {
                "standard_id": s.standard_id,
                "standard_number": s.standard_number,
                "title": s.title,
                "current_version": s.current_version,
                "status": s.status,
                "category_id": s.category_id,
                "sector": s.sector,
                "year_published": s.year_published,
                "amendments_count": len(s.amendments) if s.amendments else 0,
            }
            for s in items
        ],
    }


@router.get("/standards/{standard_number}", summary="Get Complete Standard Details & Relationships")
def get_standard_details(
    standard_number: str,
    db: Session = Depends(get_db),
):
    """
    Fetch comprehensive standard details including full scope, abstracts,
    amendment timeline, certification rules, and normative/allied graph relationships.
    """
    detail = RetrievalService.get_standard_detail(standard_number=standard_number, db=db)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Standard '{standard_number}' not found in database",
        )
    return detail


@router.get("/categories", summary="List All Product Categories")
def list_categories(db: Session = Depends(get_db)):
    """Retrieve all product categories and counts of associated standards."""
    cats = db.query(ProductCategoryModel).all()
    return [
        {
            "category_id": c.category_id,
            "name": c.name,
            "description": c.description,
            "standards_count": len(c.standards) if c.standards else 0,
            "rules_count": len(c.certification_rules) if c.certification_rules else 0,
        }
        for c in cats
    ]
