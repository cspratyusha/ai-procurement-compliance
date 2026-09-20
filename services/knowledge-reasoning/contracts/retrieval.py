"""Input contract: what Part 2 (Retrieval & Ranking) hands to Part 3.

This is a proposal, not yet confirmed by Teammate 2 — see INTEGRATION.md.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator

from contracts.is_number import ISNumberStr


class RetrievalCandidate(BaseModel):
    is_number: ISNumberStr  # canonicalised on assignment, see contracts/is_number.py
    title: str
    score: float
    match_reason: Literal["dense", "sparse", "hybrid", "reranked"]
    snippet: str | None = None

    @field_validator("score")
    @classmethod
    def _score_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"score must be in [0.0, 1.0], got {v}")
        return v


class RetrievalResult(BaseModel):
    query_id: UUID
    normalised_query: str  # post-preprocessing, English
    original_query: str
    original_language: str  # BCP-47
    product_category: str | None = None
    candidates: list[RetrievalCandidate]
