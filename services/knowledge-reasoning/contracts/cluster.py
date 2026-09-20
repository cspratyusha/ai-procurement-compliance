"""Output contract: Part 3's annotated standard cluster.

Two rules enforced by this module and by everything that builds a
``ValidatedCluster``:

1. Part 3 emits structure, never prose. All natural language comes from
   Part 5. ``OverlapWarning.explanation_hint`` is a structured hint, not a
   sentence.
2. Nothing is unexplained. Every ``ClusterMember`` carries ``role`` and
   ``path``, so both the UI and the LLM can answer "why is this here?"
   without guessing.

Relationship-type names mirror ``Solution_details/07_Data_Flow_And_Databases.md``
(the planning docs the team has already agreed on), not the earlier draft in
this brief — see INTEGRATION.md, decision log entry "EdgeType vocabulary".
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

from contracts.is_number import ISNumberStr, OptionalISNumberStr


class EdgeType(str, Enum):
    """Why a standard is present in a cluster — the traversal edge that found it."""

    NORMATIVE_REFERENCE = "normative_reference"
    TEST_METHOD_FOR = "test_method_for"
    TERMINOLOGY_FOR = "terminology_for"
    SAFETY_REQUIREMENT_FOR = "safety_requirement_for"
    INSTALLATION_GUIDE_FOR = "installation_guide_for"
    # Confirmed in Teammate 1's real corpus during integration (Stage C) —
    # a product standard pointing at its own design/construction code,
    # the same real direction and role as INSTALLATION_GUIDE_FOR ("sibling"
    # per integration decision 3), just a distinct label in their data.
    DESIGN_CODE_FOR = "design_code_for"
    # Planning docs are silent on RELATED_PRODUCT and AMENDED_BY; kept from
    # the original brief. AMENDED_BY confirmed real during integration
    # (Stage C: "IS 4984:2016/Amd 1" is a separate Standard node linked
    # this way) — RELATED_PRODUCT itself is still unconfirmed.
    RELATED_PRODUCT = "related_product"
    AMENDED_BY = "amended_by"
    # Three more real, domain-specific "related" variants found in the
    # corpus (Stage C) — kept distinct from RELATED_PRODUCT rather than
    # merged into it, since Teammate 1 chose to label them distinctly and
    # collapsing that signal is a decision for the team's vocabulary
    # proposal, not something to do silently on my side.
    COMPLEMENTARY_PART = "complementary_part"
    RELATED_PPE = "related_ppe"
    RELATED_PIPING = "related_piping"
    # The fallback bucket (integration decision 3): any relationship type
    # in real data with no configured mapping lands here rather than being
    # silently dropped. Never assigned deliberately — see
    # GraphRepository.expand's docstring and ports.types.ExpansionResult.
    RELATED_UNCLASSIFIED = "related_unclassified"
    # Note: SUPERSEDED_BY is deliberately not a cluster-membership role — a
    # superseded standard is not "in" the cluster via this edge, it is a
    # version-status fact about a member. See VersionStatus below.


class Amendment(BaseModel):
    amendment_number: str
    date_issued: date
    change_summary: str


class VersionStatus(BaseModel):
    current_edition: str
    is_current: bool
    superseded_by: OptionalISNumberStr = None
    withdrawn: bool
    amendments: list[Amendment] = []
    last_verified: datetime
    data_verified: bool  # False = came from unverified fixture, never hide this
    # Set alongside data_verified whenever it's False, explaining *why* not
    # (never set when data_verified is True — see
    # PostgresStandardsRepository's verified-derivation for the exact rule
    # and its own caveat: Teammate 1's real `source_checked_at` currently
    # means "row last written", not "checked against BIS", so today this
    # under-reports risk more often than it should — real, not decorative,
    # evidence for the team, not a solved problem).
    verification_reason: str | None = None


class CertificationRequirement(BaseModel):
    scheme: Literal["ISI", "CRS", "HALLMARKING", "NONE", "UNKNOWN"]
    mandatory: bool
    required_evidence: list[str] = []
    notification_reference: str | None = None
    effective_date: date | None = None
    source_url: str | None = None
    # Derived, not settable — see the model validator below. False means
    # `required_evidence`/`effective_date`/`source_url` (if populated at
    # all) came from somewhere other than a citable BIS notification, and
    # Part 5 must not state them as fact — the highest-risk hallucination
    # surface in the system, since a fabricated evidence requirement reads
    # as completely plausible and could go straight into a tender's
    # evaluation criteria. See generation/certification_guard.py.
    traceable: bool = False

    @field_validator("scheme")
    @classmethod
    def _unknown_is_never_silently_none(cls, v: str) -> str:
        # Documents the invariant enforced by the certification mapper
        # (Phase 3): an unmapped product category returns UNKNOWN, never NONE.
        # NONE is only valid when a rule explicitly says "no certification
        # applies", not as a default for "we don't know".
        return v

    @model_validator(mode="after")
    def _traceable_matches_notification_reference(self) -> "CertificationRequirement":
        self.traceable = self.notification_reference is not None
        return self


class ClusterMember(BaseModel):
    is_number: ISNumberStr
    title: str
    scope_text: str | None = None
    role: EdgeType  # why it is here
    # Cluster-assembly (Phase 2, not built yet) must score a
    # role=RELATED_UNCLASSIFIED member lower than a confidently-typed one —
    # Part 5 uses this to phrase it cautiously ("related to", never "is the
    # test method for"). Not enforced here since relevance is computed
    # upstream, not validated against role; documented so the constraint
    # isn't lost before that code exists.
    relevance: float
    path: list[str]  # how it was reached, seed -> ... -> this member
    hop_distance: int
    version: VersionStatus
    certification: CertificationRequirement
    trust_score: float | None = None  # None until Part 3 item 7 is implemented

    @field_validator("path")
    @classmethod
    def _canonicalise_path(cls, v: list[str]) -> list[str]:
        from contracts.is_number import canonicalise_is_number

        return [canonicalise_is_number(p) for p in v]

    @field_validator("hop_distance")
    @classmethod
    def _hop_distance_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"hop_distance must be >= 0, got {v}")
        return v


class OverlapWarning(BaseModel):
    is_a: ISNumberStr
    is_b: ISNumberStr
    overlap_score: float
    explanation_hint: str  # structured, NOT prose
    source: Literal["curated", "computed"]  # see decision 3 in INTEGRATION.md


class GraphStats(BaseModel):
    """Traversal telemetry — what the expansion actually did, for debugging
    "why did/didn't this standard appear" without re-running the traversal."""

    seeds: list[str]
    max_hops: int
    nodes_visited: int
    edges_traversed: int
    hub_nodes_excluded: list[str] = []
    truncated: bool = False
    traversal_ms: float | None = None
    # Every relationship-type string the traversal encountered that had no
    # configured mapping (see EdgeType.RELATED_UNCLASSIFIED, decision 3),
    # with how many times each was seen. Surfaced here, not just logged, so
    # a gap in the vocabulary is visible in the response itself — silently
    # dropping a third of real edges was the exact failure this exists to
    # prevent. Populated from GraphRepository.expand's
    # ExpansionResult.unmapped_edge_types by cluster-assembly (Phase 2).
    unmapped_edge_types: dict[str, int] = {}

    @field_validator("seeds")
    @classmethod
    def _canonicalise_seeds(cls, v: list[str]) -> list[str]:
        from contracts.is_number import canonicalise_is_number

        return [canonicalise_is_number(s) for s in v]


class ValidatedCluster(BaseModel):
    query_id: UUID
    primary: list[ClusterMember]
    allied: list[ClusterMember]
    overlaps: list[OverlapWarning] = []
    orphan: bool
    orphan_reason: str | None = None
    confidence: float
    graph_stats: GraphStats

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {v}")
        return v
