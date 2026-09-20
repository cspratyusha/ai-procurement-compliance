"""Output contract: Part 5's generated response.

Built in Phase 1 alongside the other contracts (per the brief: "contracts —
build these before anything else"); the generation logic that populates
these models is Phase 4 work.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, field_validator

from contracts.is_number import ISNumberStr


class StandardExplanation(BaseModel):
    is_number: ISNumberStr
    why_recommended: str
    risk_if_omitted: str | None = None


class VersionNote(BaseModel):
    is_number: ISNumberStr
    note: str  # plain-language version/supersession/amendment summary


class GroundingReport(BaseModel):
    """The hallucination guard's audit trail for one generation call.

    Built by Phase 4's guard, not hand-authored — every field here is
    evidence, not a claim, so the guard's own tests can assert on it
    directly (e.g. "a fabricated number ends up in rejected_numbers, not
    cited_numbers").
    """

    context_is_numbers: list[str]  # every IS number available in the grounding context
    cited_is_numbers: list[str]  # numbers that survived into the final output
    rejected_is_numbers: list[str] = []  # numbers extracted from a draft, not in context
    regenerated: bool = False  # a corrective regeneration pass was triggered
    passed: bool  # False means output was suppressed, not returned ungrounded

    @field_validator(
        "context_is_numbers", "cited_is_numbers", "rejected_is_numbers"
    )
    @classmethod
    def _canonicalise_list(cls, v: list[str]) -> list[str]:
        from contracts.is_number import canonicalise_is_number

        return [canonicalise_is_number(s) for s in v]


class GeneratedResponse(BaseModel):
    query_id: UUID
    summary: str
    explanations: list[StandardExplanation]
    version_notes: list[VersionNote] = []
    overlap_notes: list[str] = []
    certification_notes: list[str] = []
    clause_text: str | None = None
    language: str  # BCP-47
    grounding_report: GroundingReport
