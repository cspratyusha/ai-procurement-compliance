"""In-memory `GraphRepository` backed by fixtures/*.yaml, via networkx.

This is the implementation business logic (Phase 2/3) tests against by
default — no Neo4j required. It honours exactly the same `RelSpec`
direction semantics as `graph/queries.py`'s generated Cypher (see
`_neighbors`), so swapping this for `Neo4jGraphRepository` never changes
traversal *behaviour*, only where the data comes from.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from contracts.cluster import EdgeType
from knowledge_reasoning.adapters.fixture.fixture_data import (
    DEFAULT_FIXTURES_ROOT,
    FixtureDomain,
    load_all_fixture_domains,
)
from knowledge_reasoning.config.schema_map import Direction, SchemaMap
from knowledge_reasoning.ports.types import (
    CuratedOverlap,
    ExpansionResult,
    GraphPath,
    SupersessionEdge,
)


class FixtureGraphRepository:
    def __init__(
        self,
        schema: SchemaMap,
        domains: list[FixtureDomain] | None = None,
    ) -> None:
        self._schema = schema
        self._rel_keys = {e.value for e in EdgeType if e.value in schema.relationship_types}
        self._domains = domains or load_all_fixture_domains(DEFAULT_FIXTURES_ROOT)
        self._graph = nx.MultiDiGraph()
        for domain in self._domains:
            for node in domain.nodes:
                self._graph.add_node(
                    node.is_number,
                    title=node.title,
                    scope_text=node.scope_text,
                    status=node.status,
                    edition=node.edition,
                    category=node.category,
                    verified=node.verified,
                )
            for edge in domain.edges:
                self._graph.add_edge(
                    edge.from_is_number,
                    edge.to_value,
                    type=edge.type,
                    verified=edge.verified,
                    overlap_score=edge.overlap_score,
                )

    def _neighbors(self, seed: str, rel_key: str, direction: Direction) -> list[str]:
        found = []
        if direction in ("outgoing", "either"):
            for _, target, data in self._graph.out_edges(seed, data=True):
                if data.get("type") == rel_key:
                    found.append(target)
        if direction in ("incoming", "either"):
            for source, _, data in self._graph.in_edges(seed, data=True):
                if data.get("type") == rel_key:
                    found.append(source)
        return found

    def _classify(self, rel_key: str, actual_direction: Direction) -> EdgeType | None:
        """Decide whether an edge (found in the `actual_direction` sense —
        'outgoing' if the current node is its source, 'incoming' if it's
        the target) counts as a cluster-membership hop, and if so, which
        role. Returns None for a recognised-but-non-membership type
        (superseded_by/overlaps_scope_with/belongs_to — read via their own
        accessors, never via expand()) or a direction mismatch. A type
        that isn't in schema_map.relationship_types at all is the fallback
        bucket (decision 3) — always accepted, regardless of direction,
        since we have no configured direction to check it against.
        """
        if rel_key not in self._schema.relationship_types:
            return EdgeType.RELATED_UNCLASSIFIED
        if rel_key not in self._rel_keys:
            return None  # known, but not a cluster-membership role
        configured = self._schema.rel(rel_key).direction
        if configured == "either" or configured == actual_direction:
            return EdgeType(rel_key)
        return None

    def expand(self, seeds: list[str], max_hops: int) -> ExpansionResult:
        results: list[GraphPath] = []
        unmapped_edge_types: dict[str, int] = {}
        visited: set[str] = set(seeds)
        frontier: list[tuple[str, list[str]]] = [(s, [s]) for s in seeds]

        for hop in range(1, max_hops + 1):
            next_frontier: list[tuple[str, list[str]]] = []
            for node, path in frontier:
                if node not in self._graph:
                    continue  # dangling reference: seed/hop target not a real node
                candidates: list[tuple[str, str, str]] = []  # (neighbour, rel_key, direction)
                for _, target, data in self._graph.out_edges(node, data=True):
                    candidates.append((target, data.get("type"), "outgoing"))
                for source, _, data in self._graph.in_edges(node, data=True):
                    candidates.append((source, data.get("type"), "incoming"))

                for neighbour, rel_key, actual_direction in candidates:
                    if neighbour in visited:
                        continue
                    role = self._classify(rel_key, actual_direction)
                    if role is None:
                        continue
                    if role is EdgeType.RELATED_UNCLASSIFIED:
                        unmapped_edge_types[rel_key] = unmapped_edge_types.get(rel_key, 0) + 1
                    visited.add(neighbour)
                    new_path = path + [neighbour]
                    results.append(
                        GraphPath(target=neighbour, role=role, path=new_path, hop_distance=hop)
                    )
                    next_frontier.append((neighbour, new_path))
            frontier = next_frontier
            if not frontier:
                break

        return ExpansionResult(paths=results, unmapped_edge_types=unmapped_edge_types)

    def get_supersession(self, is_number: str) -> SupersessionEdge:
        spec = self._schema.rel("superseded_by")
        forward_dir = spec.direction
        backward_dir = {"outgoing": "incoming", "incoming": "outgoing", "either": "either"}[
            forward_dir
        ]

        if is_number not in self._graph:
            return SupersessionEdge(is_number=is_number, superseded_by=None, supersedes=[])

        successors = self._neighbors(is_number, "superseded_by", forward_dir)
        predecessors = self._neighbors(is_number, "superseded_by", backward_dir)

        return SupersessionEdge(
            is_number=is_number,
            superseded_by=successors[0] if successors else None,
            supersedes=predecessors,
        )

    def get_curated_overlaps(self, is_numbers: list[str]) -> list[CuratedOverlap]:
        number_set = set(is_numbers)
        seen: set[frozenset[str]] = set()
        overlaps: list[CuratedOverlap] = []
        for u, v, data in self._graph.edges(data=True):
            if data.get("type") != "overlaps_scope_with":
                continue
            if u not in number_set or v not in number_set:
                continue
            pair = frozenset((u, v))
            if pair in seen:
                continue
            seen.add(pair)
            is_a, is_b = sorted((u, v))
            overlaps.append(
                CuratedOverlap(
                    is_a=is_a,
                    is_b=is_b,
                    overlap_score=data.get("overlap_score") or 1.0,
                )
            )
        return overlaps

    def get_category_via_edge(self, is_number: str) -> str | None:
        if is_number not in self._graph:
            return None
        for target in self._neighbors(is_number, "belongs_to", "outgoing"):
            return target
        return None
