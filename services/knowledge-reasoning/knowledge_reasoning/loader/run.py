"""CLI entry point: load fixtures/*.yaml into the databases KR_* env vars
point at (the dev docker-compose stack, by default).

Usage:
    python -m knowledge_reasoning.loader.run
    python -m knowledge_reasoning.loader.run --allow-unverified-in-production
"""

from __future__ import annotations

import argparse
import sys

import psycopg
from neo4j import GraphDatabase

from knowledge_reasoning.adapters.fixture.fixture_data import (
    DEFAULT_FIXTURES_ROOT,
    load_all_fixture_domains,
)
from knowledge_reasoning.config.schema_map import load_schema_map
from knowledge_reasoning.config.settings import load_settings
from knowledge_reasoning.db.schema import ensure_postgres_schema
from knowledge_reasoning.loader.fixture_loader import load_into_neo4j, load_into_postgres


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-unverified-in-production",
        action="store_true",
        help="override the production guard (see loader/fixture_loader.py)",
    )
    args = parser.parse_args()

    settings = load_settings()
    schema = load_schema_map(settings.schema_map_path)
    domains = load_all_fixture_domains(DEFAULT_FIXTURES_ROOT)
    allow_unverified = (
        args.allow_unverified_in_production or settings.allow_unverified_in_production
    )

    if not settings.postgres_dsn:
        print("KR_POSTGRES_DSN not set — nothing to load into Postgres.", file=sys.stderr)
        return 1

    with psycopg.connect(settings.postgres_dsn) as conn:
        ensure_postgres_schema(conn)
        postgres_report = load_into_postgres(
            conn,
            schema,
            domains,
            env=settings.env,
            allow_unverified_in_production=allow_unverified,
        )
    print(f"Postgres: {postgres_report}")
    if postgres_report.edges_dropped_dangling:
        print(
            f"Dropped {len(postgres_report.edges_dropped_dangling)} dangling edge(s) "
            f"(source or target not present as a node): "
            f"{postgres_report.edges_dropped_dangling}"
        )

    # Neo4j is optional — there is no real Neo4j data anywhere as of
    # integration Stage A/B, so postgres is the default graph backend (see
    # settings.py). Still loaded here if configured, so switching
    # KR_GRAPH_BACKEND=neo4j later has real data to point at.
    if settings.neo4j_uri:
        auth = (settings.neo4j_user, settings.neo4j_password) if settings.neo4j_user else None
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=auth)
        neo4j_report = load_into_neo4j(
            driver,
            schema,
            domains,
            env=settings.env,
            allow_unverified_in_production=allow_unverified,
        )
        driver.close()
        print(f"Neo4j:    {neo4j_report}")
    else:
        print("KR_NEO4J_URI not set — skipped Neo4j load (postgres is the default graph backend).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
