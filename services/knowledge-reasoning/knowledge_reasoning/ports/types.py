"""Internal repository-layer DTOs.

These are distinct from `contracts/` on purpose: `contracts/` is the
external boundary shared with Teammates 2 and 4 and must stay stable once
proposed. These types are Part 3's own internal plumbing between the
port interfaces and the adapters that implement them — they can change
freely as the graph/db expansion algorithms (Phase 2/3) evolve, without
touching anything a teammate depends on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from contracts.cluster import EdgeType

StandardStatus = Literal["active", "superseded", "withdrawn"]


@dataclass(frozen=True)
class GraphPath:
    """One reachable node from a traversal, as returned by
    `GraphRepository.expand()`."""

    target: str  # canonical is_number reached
    role: EdgeType  # edge type of the last hop — why it's included
    path: list[str]  # seed -> ... -> target, inclusive of both ends
    hop_distance: int


@dataclass(frozen=True)
class ExpansionResult:
    """`GraphRepository.expand()`'s full return value.

    `unmapped_edge_types` (decision 3, integration Stage D) counts every
    relationship-type string the traversal actually encountered that had
    no configured `schema_map` mapping — each such edge still contributes
    a `GraphPath` (role=EdgeType.RELATED_UNCLASSIFIED), it just isn't
    silently dropped the way an unrecognised type was before this existed.
    Cluster-assembly (Phase 2) copies this into
    `contracts.cluster.GraphStats.unmapped_edge_types` so it's visible in
    the response, not just in logs.
    """

    paths: list[GraphPath]
    unmapped_edge_types: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class StandardMetadata:
    is_number: str
    title: str
    scope_text: str | None
    status: StandardStatus
    edition: str | None
    category: str | None
    verified: bool
    # Raw ISO-date string (Teammate 1's real `last_amended` column is TEXT,
    # not DATE — confirmed Stage A/B). Used both for display and to derive
    # amendment dates when an amendment is modelled as a separate,
    # AMENDED_BY-linked Standard rather than an `amendments` table row —
    # see PostgresStandardsRepository.get_version_status.
    last_amended: str | None = None


@dataclass(frozen=True)
class SupersessionEdge:
    """Direct (one-hop) supersession neighbours of a standard, read with the
    direction asserted by `schema_map.RELATIONSHIP_TYPES["superseded_by"]`.
    Chain-walking to the ultimate current edition is Phase 3 business logic
    built on top of this primitive.
    """

    is_number: str
    superseded_by: str | None  # direct successor, if any (this node is old)
    supersedes: list[str] = field(default_factory=list)  # direct predecessors


@dataclass(frozen=True)
class CuratedOverlap:
    """A scope-overlap edge curated by Teammate 1 in the graph, as opposed to
    one Part 3 computes itself from scope text (see decision 3, INTEGRATION.md).
    """

    is_a: str
    is_b: str
    overlap_score: float


@dataclass(frozen=True)
class CertificationRuleRow:
    """One row of the certification_rules table. Read-only data access; the
    deterministic mapping logic that consumes these (raw scheme string ->
    contracts.cluster.CertificationRequirement's closed
    ISI/CRS/HALLMARKING/NONE/UNKNOWN vocabulary) is Phase 3, not built yet.

    `scheme` is deliberately `str`, not a closed Literal: Teammate 1's real
    data (confirmed Stage A/B) stores free text ("BIS Product
    Certification"), not the closed vocabulary — narrowing that string
    into ISI/CRS/HALLMARKING is exactly what the not-yet-built mapper is
    for, and pretending it's already closed here would just move the
    mismatch to construction time instead of mapping time.
    """

    product_category: str
    standard_is_number: str | None
    scheme: str
    mandatory: bool
    required_evidence: list[str]
    notification_reference: str | None
    effective_date: date | None
    source_url: str | None
    verified: bool
