from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class Standard(BaseModel):
    """Pydantic model representing an Indian Standard (BIS) document specification."""
    id: str = Field(..., description="Unique internal identifier, e.g., IS-ELEC-001")
    number: str = Field(..., description="Realistic IS-style numbering, e.g. 'IS 1554 (Part 1):2019'")
    title: str = Field(..., description="Full official title of the standard")
    scope: str = Field(..., description="1-3 sentences in formal regulatory tone: 'This standard covers...'")
    description: str = Field(..., description="2-4 sentences, use-case oriented technical summary")
    category: str = Field(..., description="Product/domain classification category")
    version: str = Field(..., description="Version or revision string, e.g. 'Third Revision'")
    last_amended: str = Field(..., description="Date of the latest amendment, YYYY-MM-DD")
    status: Literal["active", "superseded"] = Field(..., description="Current validity status")
    keywords: list[str] = Field(default_factory=list, description="List of domain keywords and technical terms")
    superseded_by_number: Optional[str] = Field(
        default=None,
        description="IS number of the edition that replaced this one. May name an edition the corpus does not hold.",
    )
    withdrawn: bool = Field(
        default=False,
        description="BIS lists this edition as withdrawn. With no superseded_by_number, it has no replacement.",
    )
    withdrawal_note: Optional[str] = Field(
        default=None,
        description="BIS's reason for a withdrawal with no replacement, e.g. 'Decided by council'.",
    )
    now_in_parts: List[str] = Field(
        default_factory=list,
        description="Filled on a single standard's page: for a withdrawal with no replacement, the parts "
                    "the standard is now published in (IS 2062:2011 -> IS 2062 (Part 1):2025, (Part 2):2026).",
    )
    status_source: Optional[str] = Field(
        default=None,
        description="Where the status came from: 'bis' (BIS's record for the standard); absent when inferred from the corpus.",
    )
    provenance: Optional[str] = Field(
        default=None,
        description=(
            "Where the scope text came from: 'published_text_ocr' (the standard's own scope clause), "
            "'published_text_bis' (the scope clause of a standard published since October 2025, from the "
            "document BIS's portal links), "
            "'scope_written' (a summary written for the catalogue, number and title checked against BIS), "
            "'scope_from_previous_edition' (a new edition searched with the scope clause of the edition "
            "it revises, named in scope_edition), 'number_and_title_only' (no scope held)."
        ),
    )
    bis_summary: Optional[str] = Field(
        default=None,
        description="BIS's full plain-language summary of the standard, where it publishes one; the description holds its opening.",
    )
    description_source: Optional[str] = Field(
        default=None,
        description="'bis_summary' when the description is BIS's published plain-language summary of the standard.",
    )
    scope_edition: Optional[str] = Field(
        default=None,
        description="For provenance 'scope_from_previous_edition': the earlier edition the scope text is from.",
    )
    published_on: Optional[str] = Field(
        default=None, description="Publication date from BIS's standards portal, for editions published since October 2025.")
    withdrawn_on: Optional[str] = Field(default=None, description="Date BIS withdrew this edition, where its portal gives one.")
    replacement_source: Optional[str] = Field(
        default=None,
        description=(
            "'bis_newer_edition' when BIS's record for this edition names no replacement and "
            "superseded_by_number is the newer edition BIS lists as current; absent when BIS named it."
        ),
    )
