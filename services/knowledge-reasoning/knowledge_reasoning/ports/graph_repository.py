"""Abstraction over Teammate 1's standards graph (Postgres by default — see
`config/settings.py` — or Neo4j).

`expand` does connectivity only in Phase 1 (unweighted BFS, cycle-safe,
direction- and hop-limit-respecting) — edge-type weighting, hub-degree
penalties, and result-cap truncation are Phase 2. The signature is already
shaped for that: `max_hops` is configurable now, `GraphStats` (contracts)
already has the fields Phase 2 needs to report what it did.

`expand` returns an `ExpansionResult`, not a bare list: real relationship
data (integration Stage C) uses relationship-type strings with no
configured mapping for roughly a third of edges. Those edges are never
silently dropped — each still contributes a `GraphPath` tagged
`role=EdgeType.RELATED_UNCLASSIFIED`, and `unmapped_edge_types` counts
which raw type strings triggered the fallback, so a vocabulary gap is
visible in the response (via `GraphStats`, once cluster-assembly copies it
across), not just in logs.

`get_supersession` and `get_curated_overlaps` are direction/provenance-
sensitive primitives kept separate from `expand` on purpose — see
`standards_repository.py` and decision 3 in INTEGRATION.md.
"""

from __future__ import annotations

from typing import Protocol

from knowledge_reasoning.ports.types import (
    CuratedOverlap,
    ExpansionResult,
    SupersessionEdge,
)


class GraphRepository(Protocol):
    def expand(self, seeds: list[str], max_hops: int) -> ExpansionResult: ...

    def get_supersession(self, is_number: str) -> SupersessionEdge: ...

    def get_curated_overlaps(self, is_numbers: list[str]) -> list[CuratedOverlap]: ...

    def get_category_via_edge(self, is_number: str) -> str | None: ...
