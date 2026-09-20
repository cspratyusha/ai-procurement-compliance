"""CLI: report every distinct relationship type in the configured graph
backend's data, and whether `config/schema_map.py` has a mapping for it.

The fallback bucket (integration decision 3) means an unmapped type is
never silently dropped any more — but "not dropped" isn't the same as
"noticed". This is the tool for noticing: run it after any new data lands
to see exactly which relationship-type strings the vocabulary doesn't
cover yet, before they show up as EdgeType.RELATED_UNCLASSIFIED members
in a response.

Usage:
    python -m knowledge_reasoning.loader.report_relationship_types
    python -m knowledge_reasoning.loader.report_relationship_types --backend postgres
"""

from __future__ import annotations

import argparse
import sys

from knowledge_reasoning.adapters.fixture.fixture_data import (
    DEFAULT_FIXTURES_ROOT,
    load_all_fixture_domains,
)
from knowledge_reasoning.config.schema_map import SchemaMap, load_schema_map
from knowledge_reasoning.config.settings import load_settings


def fixture_relationship_type_counts() -> dict[str, int]:
    """Raw edge `type` values as they appear in fixtures/*.yaml — the
    schema_map *key* namespace (e.g. "normative_reference"), not the raw
    Cypher/SQL name namespace."""
    counts: dict[str, int] = {}
    for domain in load_all_fixture_domains(DEFAULT_FIXTURES_ROOT):
        for edge in domain.edges:
            counts[edge.type] = counts.get(edge.type, 0) + 1
    return counts


def postgres_relationship_type_counts(dsn: str, schema: SchemaMap) -> dict[str, int]:
    """Raw `standard_relationships.type` values — the raw Cypher/SQL name
    namespace (e.g. "NORMATIVE_REFERENCE"), not the schema_map key
    namespace."""
    import psycopg

    table = schema.table("standard_relationships")
    type_col = schema.column("standard_relationships", "type")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {type_col}, count(*) FROM {table} GROUP BY {type_col}")
        return {row[0]: row[1] for row in cur.fetchall()}


def known_keys(schema: SchemaMap) -> set[str]:
    """schema_map key namespace — what fixture data's `type` field uses."""
    return set(schema.relationship_types.keys())


def known_names(schema: SchemaMap) -> set[str]:
    """Raw Cypher/SQL name namespace — what Postgres/Neo4j actually store."""
    return {spec.name for spec in schema.relationship_types.values()}


def report(counts: dict[str, int], known: set[str]) -> int:
    """Prints a table, returns the count of unmapped types found."""
    unmapped = 0
    width = max((len(k) for k in counts), default=10)
    print(f"{'TYPE'.ljust(width)}  COUNT  MAPPED?")
    for rel_type, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        mapped = rel_type in known
        if not mapped:
            unmapped += 1
        print(f"{rel_type.ljust(width)}  {count:>5}  {'yes' if mapped else 'NO — falls back to RELATED_UNCLASSIFIED'}")
    return unmapped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend", choices=["fixture", "postgres"], default=None,
        help="defaults to KR_GRAPH_BACKEND (fixture and neo4j both report fixture data; "
             "pass --backend postgres explicitly to inspect a live Postgres instead)",
    )
    args = parser.parse_args()

    settings = load_settings()
    schema = load_schema_map(settings.schema_map_path)
    backend = args.backend or ("postgres" if settings.graph_backend == "postgres" else "fixture")

    if backend == "postgres":
        if not settings.postgres_dsn:
            print("KR_POSTGRES_DSN not set.", file=sys.stderr)
            return 1
        counts = postgres_relationship_type_counts(settings.postgres_dsn, schema)
        known = known_names(schema)
    else:
        counts = fixture_relationship_type_counts()
        known = known_keys(schema)

    unmapped = report(counts, known)
    if unmapped:
        print(f"\n{unmapped} relationship type(s) have no schema_map mapping.")
    else:
        print("\nEvery relationship type in this data is mapped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
