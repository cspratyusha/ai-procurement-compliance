"""Pydantic models for API responses."""

from __future__ import annotations

from pydantic import BaseModel


class Standard(BaseModel):
    id: str
    number: str
    title: str
    scope: str
    description: str
    category: str
    version: str
    last_amended: str
    status: str
    keywords: list[str]


class Relationship(BaseModel):
    source_id: str
    target_id: str
    type: str


class StandardDetail(Standard):
    relationships: list[Relationship]


class Amendment(BaseModel):
    amendment_id: str
    standard_id: str
    amendment_number: int
    date_issued: str | None
    change_summary: str


class CertificationRule(BaseModel):
    category: str
    scheme_type: str
    mandatory: bool


class SearchResult(Standard):
    rank: float


class SemanticSearchResult(Standard):
    dense_score: float


class HybridSearchResult(Standard):
    dense_score: float
    bm25_score: float
    hybrid_score: float
    cross_encoder_score: float | None = None
