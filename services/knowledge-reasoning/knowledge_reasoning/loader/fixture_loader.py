"""Idempotent loader: fixtures/*.yaml -> Neo4j + Postgres.

Idempotent because every write is a MERGE (Neo4j) or an upsert with
ON CONFLICT (Postgres) — re-running the loader against the same data is
always safe, which matters both for local dev iteration and because "the
loader takes Teammate 1's real data unchanged, in the same format" only
holds if it can be re-run freely as that data changes.

Production guard (decision 5): refuses to write any `verified: false`
record into anything the caller says is `KR_ENV=production`, unless
`allow_unverified_in_production=True` is passed explicitly. This exists so
placeholder fixture data cannot reach a real deployment or a demo by
accident — the check runs before any write, not interleaved with them, so
a guard failure never leaves a partial load behind.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from neo4j import Driver
import psycopg

from knowledge_reasoning.adapters.fixture.fixture_data import FixtureDomain
from knowledge_reasoning.config.schema_map import SchemaMap
from knowledge_reasoning.db import queries as db_queries
from knowledge_reasoning.graph import queries as graph_queries

logger = logging.getLogger(__name__)


class ProductionUnverifiedDataError(RuntimeError):
    """Raised when a production-flagged load would write verified=false
    records without an explicit override. See module docstring."""


@dataclass
class LoadReport:
    nodes_written: int = 0
    edges_written: int = 0
    edges_dropped_dangling: list[tuple[str, str, str]] = field(default_factory=list)
    # Only ever populated by load_into_neo4j: unlike Postgres (where an
    # unmapped type is just a VALUE bound as a parameter),
    # graph/queries.py's Cypher relationship type is interpolated directly
    # into the query text, and that file's invariant is "only validated
    # schema names get interpolated, never raw data" — so an unmapped type
    # can't safely be MERGEd in. Tracked here (never silently dropped, per
    # decision 4) rather than raising, since Neo4j has no real data or
    # unmapped-type read-side support yet (see Neo4jGraphRepository.expand
    # docstring) and shouldn't block loading everything else.
    edges_skipped_unmapped_type: list[tuple[str, str, str]] = field(default_factory=list)
    amendments_written: int = 0
    certification_rules_written: int = 0


def _guard_unverified(
    domains: list[FixtureDomain], env: str, allow_unverified_in_production: bool
) -> None:
    if env != "production" or allow_unverified_in_production:
        return
    for domain in domains:
        if any(not n.verified for n in domain.nodes) or any(
            not e.verified for e in domain.edges
        ):
            raise ProductionUnverifiedDataError(
                f"domain {domain.name!r} contains verified=false records and "
                f"env=production — refusing to load. Pass "
                f"allow_unverified_in_production=True (or set "
                f"KR_ALLOW_UNVERIFIED_IN_PRODUCTION=true) only if you are "
                f"certain this is intentional."
            )


def load_into_neo4j(
    driver: Driver,
    schema: SchemaMap,
    domains: list[FixtureDomain],
    *,
    env: str = "dev",
    allow_unverified_in_production: bool = False,
) -> LoadReport:
    _guard_unverified(domains, env, allow_unverified_in_production)

    report = LoadReport()
    merge_standard = graph_queries.build_merge_standard_query(schema)
    merge_category = graph_queries.build_merge_category_query(schema)
    merge_belongs_to = graph_queries.build_merge_belongs_to_query(schema)

    with driver.session() as session:
        node_numbers: set[str] = set()
        category_names: set[str] = set()

        for domain in domains:
            for node in domain.nodes:
                session.run(
                    merge_standard,
                    is_number=node.is_number,
                    title=node.title,
                    scope_text=node.scope_text,
                    status=node.status,
                    edition=node.edition,
                    verified=node.verified,
                )
                report.nodes_written += 1
                node_numbers.add(node.is_number)
                if node.category:
                    category_names.add(node.category)

        for category_name in category_names:
            session.run(merge_category, category_name=category_name)

        for domain in domains:
            for node in domain.nodes:
                if node.category:
                    session.run(
                        merge_belongs_to, is_number=node.is_number, category_name=node.category
                    )

            for edge in domain.edges:
                if edge.type == "belongs_to":
                    session.run(merge_category, category_name=edge.to_value)
                    session.run(
                        merge_belongs_to, is_number=edge.from_is_number, category_name=edge.to_value
                    )
                    report.edges_written += 1
                    continue

                if edge.from_is_number not in node_numbers or edge.to_value not in node_numbers:
                    report.edges_dropped_dangling.append(
                        (edge.type, edge.from_is_number, edge.to_value)
                    )
                    continue

                if edge.type not in schema.relationship_types:
                    logger.warning(
                        "Skipping unmapped relationship type %r (%s -> %s) for "
                        "Neo4j — no schema_map entry, and graph/queries.py can "
                        "only interpolate validated schema names into Cypher. "
                        "Recorded in edges_skipped_unmapped_type, not dropped "
                        "silently. The Postgres loader writes this same edge.",
                        edge.type,
                        edge.from_is_number,
                        edge.to_value,
                    )
                    report.edges_skipped_unmapped_type.append(
                        (edge.type, edge.from_is_number, edge.to_value)
                    )
                    continue

                merge_rel = graph_queries.build_merge_relationship_query(schema, edge.type)
                session.run(
                    merge_rel,
                    from_is_number=edge.from_is_number,
                    to_is_number=edge.to_value,
                    verified=edge.verified,
                    overlap_score=edge.overlap_score if edge.overlap_score is not None else 1.0,
                )
                report.edges_written += 1

    return report


def load_into_postgres(
    conn: psycopg.Connection,
    schema: SchemaMap,
    domains: list[FixtureDomain],
    *,
    env: str = "dev",
    allow_unverified_in_production: bool = False,
) -> LoadReport:
    _guard_unverified(domains, env, allow_unverified_in_production)

    report = LoadReport()
    upsert_standard = db_queries.build_upsert_standard_query(schema)
    set_superseded_by = db_queries.build_set_superseded_by_query(schema)
    upsert_amendment = db_queries.build_upsert_amendment_query(schema)
    upsert_cert_rule = db_queries.build_upsert_certification_rule_query(schema)
    upsert_relationship = db_queries.build_upsert_standard_relationship_query(schema)

    with conn.cursor() as cur:
        node_numbers: set[str] = set()

        for domain in domains:
            for node in domain.nodes:
                cur.execute(
                    upsert_standard,
                    {
                        # Teammate 1's real PK has no default/serial — the
                        # canonical IS number is a stable, idempotent id.
                        "id": node.is_number,
                        "is_number": node.is_number,
                        "title": node.title,
                        "scope_text": node.scope_text,
                        "status": node.status,
                        "edition": node.edition,
                        "last_amended": node.last_amended,
                        "category": node.category,
                    },
                )
                report.nodes_written += 1
                node_numbers.add(node.is_number)

        for domain in domains:
            for edge in domain.edges:
                if edge.type == "superseded_by":
                    # Confirmed against real Teammate 1 data (integration
                    # Stage B/C): a supersession fact is written BOTH ways —
                    # as the standards.superseded_by_id FK (what
                    # PostgresStandardsRepository.get_version_status reads,
                    # matching "Postgres is source of truth") AND as a
                    # SUPERSEDED_BY row in standard_relationships (what
                    # PostgresGraphRepository.get_supersession reads, for
                    # parity with the Neo4j/fixture graph primitives). Their
                    # own scripts/ingest.py does the same: superseded_by_id
                    # comes from standards.json, the SUPERSEDED_BY edge from
                    # the separate relationships.json — same fact, twice.
                    cur.execute(
                        set_superseded_by,
                        {
                            "is_number": edge.from_is_number,
                            "superseded_by_number": edge.to_value,
                        },
                    )
                    if edge.from_is_number in node_numbers and edge.to_value in node_numbers:
                        cur.execute(
                            upsert_relationship,
                            {
                                "source_id": edge.from_is_number,
                                "target_id": edge.to_value,
                                "type": schema.rel(edge.type).name,
                            },
                        )
                    report.edges_written += 1
                elif edge.type == "belongs_to":
                    # No product_categories writes — see db/schema.sql:
                    # Teammate 1's real ingestion doesn't populate that
                    # table either; `standards.category` (already written
                    # above) is the real, working source. A belongs_to
                    # fixture edge with no matching node-level `category`
                    # would be silently lost here; nothing in this
                    # codebase's fixtures does that today.
                    continue
                else:
                    # Unlike Neo4j's MERGE (which just matches nothing for
                    # a missing endpoint), standard_relationships has real
                    # FK constraints — inserting a dangling reference would
                    # raise, not no-op. Same dangling-edge policy as the
                    # Neo4j path: record and skip, don't crash the load.
                    if edge.from_is_number not in node_numbers or edge.to_value not in node_numbers:
                        report.edges_dropped_dangling.append(
                            (edge.type, edge.from_is_number, edge.to_value)
                        )
                        continue
                    if edge.type in schema.relationship_types:
                        # Same name schema_map.RELATIONSHIP_TYPES already
                        # gives this role in Neo4j/Cypher — PostgresGraphRepository
                        # reads with the same convention.
                        rel_type_value = schema.rel(edge.type).name
                    else:
                        # Fallback bucket (decision 3/Stage E.4): an
                        # unmapped type is never silently dropped or
                        # allowed to crash the load — it's written as-is,
                        # the same raw string FixtureGraphRepository keys
                        # its unmapped_edge_types counts by, so
                        # PostgresGraphRepository.expand() classifies it
                        # into EdgeType.RELATED_UNCLASSIFIED identically
                        # across backends.
                        rel_type_value = edge.type
                        logger.warning(
                            "Loading relationship with unmapped type %r (%s -> %s) — "
                            "no schema_map entry; will surface as "
                            "RELATED_UNCLASSIFIED / unmapped_edge_types, not dropped.",
                            edge.type,
                            edge.from_is_number,
                            edge.to_value,
                        )
                    cur.execute(
                        upsert_relationship,
                        {
                            "source_id": edge.from_is_number,
                            "target_id": edge.to_value,
                            "type": rel_type_value,
                        },
                    )
                    report.edges_written += 1

            for amendment in domain.amendments:
                cur.execute(
                    upsert_amendment,
                    {
                        "id": f"{amendment.is_number}:{amendment.amendment_number}",
                        "is_number": amendment.is_number,
                        "amendment_number": amendment.amendment_number,
                        "date_issued": amendment.date_issued,
                        "change_summary": amendment.change_summary,
                    },
                )
                report.amendments_written += 1

            for rule in domain.certification_rules:
                cur.execute(
                    upsert_cert_rule,
                    {
                        "category": rule.product_category,
                        "scheme": rule.scheme,
                        "mandatory": rule.mandatory,
                    },
                )
                report.certification_rules_written += 1

    conn.commit()
    return report
