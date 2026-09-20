"""`GraphRepository` backed by a real Neo4j instance.

Every query it runs comes from `graph/queries.py` — this module never
builds Cypher itself, only binds parameters and shapes rows into the
`ports.types` DTOs. Behaviourally identical to `FixtureGraphRepository`
for the same `SchemaMap` and the same underlying data, since both honour
`RelSpec.direction` the same way.

KNOWN GAP: `expand` here only queries pre-selected known membership roles
(`self._rel_keys`), unlike `PostgresGraphRepository`/`FixtureGraphRepository`,
so `ExpansionResult.unmapped_edge_types` from this class is always empty —
it does not implement the fallback-bucket detection (decision 3). This is
deliberate, not an oversight: there is no real Neo4j data anywhere
(integration Stage A/B) to build or verify that logic against, and
Postgres is the priority target. Extend this the same way
`PostgresGraphRepository` does (fetch all relationship types, classify in
Python) if/when Teammate 1 populates Neo4j for real.
"""

from __future__ import annotations

from neo4j import Driver

from contracts.cluster import EdgeType
from knowledge_reasoning.config.schema_map import SchemaMap
from knowledge_reasoning.graph import queries
from knowledge_reasoning.ports.types import (
    CuratedOverlap,
    ExpansionResult,
    GraphPath,
    SupersessionEdge,
)


class Neo4jGraphRepository:
    def __init__(self, driver: Driver, schema: SchemaMap) -> None:
        self._driver = driver
        self._schema = schema
        self._rel_keys = [e.value for e in EdgeType if e.value in schema.relationship_types]
        self._expand_query = queries.build_expand_one_hop_query(schema, self._rel_keys)
        self._supersession_query = queries.build_supersession_query(schema)
        self._overlaps_query = queries.build_curated_overlaps_query(schema)
        self._category_query = queries.build_category_via_edge_query(schema)

    def expand(self, seeds: list[str], max_hops: int) -> ExpansionResult:
        results: list[GraphPath] = []
        visited: set[str] = set(seeds)
        frontier: dict[str, list[str]] = {s: [s] for s in seeds}

        for hop in range(1, max_hops + 1):
            if not frontier:
                break
            with self._driver.session() as session:
                rows = session.run(self._expand_query, seeds=list(frontier.keys())).data()

            next_frontier: dict[str, list[str]] = {}
            for row in rows:
                target = row["target"]
                if target is None or target in visited:
                    continue
                seed = row["seed"]
                visited.add(target)
                path = frontier[seed] + [target]
                results.append(
                    GraphPath(
                        target=target,
                        role=EdgeType(row["rel_key"]),
                        path=path,
                        hop_distance=hop,
                    )
                )
                next_frontier[target] = path
            frontier = next_frontier

        return ExpansionResult(paths=results)

    def get_supersession(self, is_number: str) -> SupersessionEdge:
        with self._driver.session() as session:
            record = session.run(self._supersession_query, is_number=is_number).single()
        if record is None:
            return SupersessionEdge(is_number=is_number, superseded_by=None, supersedes=[])
        return SupersessionEdge(
            is_number=is_number,
            superseded_by=record["superseded_by"],
            supersedes=[p for p in record["supersedes"] if p is not None],
        )

    def get_curated_overlaps(self, is_numbers: list[str]) -> list[CuratedOverlap]:
        with self._driver.session() as session:
            rows = session.run(self._overlaps_query, is_numbers=is_numbers).data()
        return [
            CuratedOverlap(is_a=r["is_a"], is_b=r["is_b"], overlap_score=r["overlap_score"])
            for r in rows
        ]

    def get_category_via_edge(self, is_number: str) -> str | None:
        with self._driver.session() as session:
            record = session.run(self._category_query, is_number=is_number).single()
        return record["category"] if record is not None else None
