"""`GraphRepository` backed by a real Postgres instance's
`standard_relationships` table, via a recursive CTE.

This exists because integration Stage A/B found there is no real Neo4j
data anywhere, and no evidence anything has ever written to it — the real
relationship data lives in Postgres. `Neo4jGraphRepository` stays selectable
by `KR_GRAPH_BACKEND=neo4j`; if Teammate 1 populates Neo4j for real later,
switching is a one-variable change and this class's callers (Phase 2/3
business logic, once built) never know the difference — that's the ports
design earning its keep, see INTEGRATION.md.

A recursive CTE is comfortably sufficient at this corpus size (tens of
standards, a dozen edges); this is not a performance compromise.

Every query comes from `db/queries.py` — this module only translates
between canonical IS numbers (the public interface, everywhere else in this
codebase) and Teammate 1's internal `standards.id` (what
`standard_relationships` actually stores), and shapes rows into the
`ports.types` DTOs. Behaviourally matched to `Neo4jGraphRepository`/
`FixtureGraphRepository`: same `RelSpec.direction` handling, same
cycle-safety (a node is never revisited, including the original seeds),
same "each reachable node once, at its shortest hop" semantics.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from contracts.cluster import EdgeType
from knowledge_reasoning.config.schema_map import SchemaMap
from knowledge_reasoning.db import queries
from knowledge_reasoning.ports.types import CuratedOverlap, ExpansionResult, GraphPath, SupersessionEdge


class PostgresGraphRepository:
    def __init__(self, dsn: str, schema: SchemaMap) -> None:
        self._dsn = dsn
        self._schema = schema
        self._expand_query = queries.build_expand_query(schema)
        self._relationship_query = queries.build_get_relationship_query(schema)
        self._overlaps_query = queries.build_get_curated_overlaps_query(schema)

        self._rel_keys = [e.value for e in EdgeType if e.value in schema.relationship_types]
        self._role_by_name = {schema.rel(k).name: EdgeType(k) for k in self._rel_keys}
        self._outgoing_types = [
            schema.rel(k).name for k in self._rel_keys if schema.rel(k).direction == "outgoing"
        ]
        self._incoming_types = [
            schema.rel(k).name for k in self._rel_keys if schema.rel(k).direction == "incoming"
        ]
        self._either_types = [
            schema.rel(k).name for k in self._rel_keys if schema.rel(k).direction == "either"
        ]
        # Every configured name, membership role or not (also
        # SUPERSEDED_BY/OVERLAPS_SCOPE_WITH/BELONGS_TO) — a type NOT in
        # this list is what the fallback bucket (decision 3) means by
        # "unmapped"; a type IN this list but not one of the three lists
        # above is a *recognised, non-membership* type, excluded from
        # expand() on purpose, not a fallback case.
        self._all_known_types = [schema.rel(k).name for k in schema.relationship_types]

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def expand(self, seeds: list[str], max_hops: int) -> ExpansionResult:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {self._schema.column('standards', 'id')} AS id, "
                f"{self._schema.column('standards', 'standard_number')} AS number "
                f"FROM {self._schema.table('standards')} "
                f"WHERE {self._schema.column('standards', 'standard_number')} = ANY(%(numbers)s::text[])",
                {"numbers": seeds},
            )
            number_to_id = {r["number"]: r["id"] for r in cur.fetchall()}
            seed_ids = [number_to_id[s] for s in seeds if s in number_to_id]
            if not seed_ids:
                return ExpansionResult(paths=[])

            cur.execute(
                self._expand_query,
                {
                    "seeds": seed_ids,
                    "max_hops": max_hops,
                    "outgoing_types": self._outgoing_types,
                    "incoming_types": self._incoming_types,
                    "either_types": self._either_types,
                    "all_known_types": self._all_known_types,
                },
            )
            rows = cur.fetchall()
            if not rows:
                return ExpansionResult(paths=[])

            all_ids = {i for r in rows for i in r["path"]}
            cur.execute(
                f"SELECT {self._schema.column('standards', 'id')} AS id, "
                f"{self._schema.column('standards', 'standard_number')} AS number "
                f"FROM {self._schema.table('standards')} "
                f"WHERE {self._schema.column('standards', 'id')} = ANY(%(ids)s::text[])",
                {"ids": list(all_ids)},
            )
            id_to_number = {r["id"]: r["number"] for r in cur.fetchall()}

        results: list[GraphPath] = []
        unmapped_edge_types: dict[str, int] = {}
        for row in rows:
            raw_type = row["role"]
            role = self._role_by_name.get(raw_type)
            if role is None:
                # The SQL already excluded recognised-but-non-membership
                # types (superseded_by etc — see build_expand_query's
                # docstring) — anything reaching here with no role match
                # is a genuinely unmapped type: the fallback bucket
                # (decision 3), not dropped.
                role = EdgeType.RELATED_UNCLASSIFIED
                unmapped_edge_types[raw_type] = unmapped_edge_types.get(raw_type, 0) + 1
            results.append(
                GraphPath(
                    target=id_to_number[row["target"]],
                    role=role,
                    path=[id_to_number[i] for i in row["path"]],
                    hop_distance=row["hop"],
                )
            )
        return ExpansionResult(paths=results, unmapped_edge_types=unmapped_edge_types)

    def get_supersession(self, is_number: str) -> SupersessionEdge:
        spec = self._schema.rel("superseded_by")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                self._relationship_query, {"is_number": is_number, "type_name": spec.name}
            )
            rows = cur.fetchall()

        # direction == "outgoing": is_number as `source` reaches its successor.
        # direction == "incoming": reversed. "either" isn't meaningful for
        # supersession and isn't used by the default schema_map.
        successor_side = "source" if spec.direction == "outgoing" else "target"
        predecessor_side = "target" if spec.direction == "outgoing" else "source"

        successors = [r["neighbour"] for r in rows if r["direction"] == successor_side]
        predecessors = [r["neighbour"] for r in rows if r["direction"] == predecessor_side]

        return SupersessionEdge(
            is_number=is_number,
            superseded_by=successors[0] if successors else None,
            supersedes=predecessors,
        )

    def get_curated_overlaps(self, is_numbers: list[str]) -> list[CuratedOverlap]:
        spec = self._schema.rel("overlaps_scope_with")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                self._overlaps_query, {"is_numbers": is_numbers, "type_name": spec.name}
            )
            rows = cur.fetchall()

        seen: set[frozenset[str]] = set()
        overlaps: list[CuratedOverlap] = []
        for r in rows:
            pair = frozenset((r["is_a"], r["is_b"]))
            if pair in seen:
                continue
            seen.add(pair)
            is_a, is_b = sorted(pair)
            # No overlap_score column in Teammate 1's real schema — same
            # default the Neo4j path uses for an absent property.
            overlaps.append(CuratedOverlap(is_a=is_a, is_b=is_b, overlap_score=1.0))
        return overlaps

    def get_category_via_edge(self, is_number: str) -> str | None:
        # No BELONGS_TO-equivalent relationship type exists in Teammate 1's
        # real standard_relationships data (confirmed Stage A/B) — category
        # is the flat `standards.category` column, read by
        # PostgresStandardsRepository directly, not via this edge fallback.
        # This is a real query against real data, not a stub: it will start
        # working the moment such an edge exists, with no code change.
        if "belongs_to" not in self._schema.relationship_types:
            return None
        spec = self._schema.rel("belongs_to")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                self._relationship_query, {"is_number": is_number, "type_name": spec.name}
            )
            rows = cur.fetchall()
        side = "source" if spec.direction == "outgoing" else "target"
        matches = [r["neighbour"] for r in rows if r["direction"] == side]
        return matches[0] if matches else None
