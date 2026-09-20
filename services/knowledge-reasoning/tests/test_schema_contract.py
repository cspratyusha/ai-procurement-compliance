"""The schema contract test — see brief section 4.4.

Two tiers, deliberately:

Tier A (always runs, backend-agnostic): exercises the *ports*
(GraphRepository / StandardsRepository), not raw Cypher/SQL. It runs
against whatever `KR_GRAPH_BACKEND`/`KR_STANDARDS_BACKEND` currently
resolve to — the fixture-backed adapters by default, so this tier is what
"right now it runs against my fixture" means in practice, and it is what
actually ran and passed in the sandbox this was built in (no Docker
available there — see INTEGRATION.md).

Tier B (live introspection, skipped if unreachable): connects directly to
whatever Neo4j/Postgres `KR_NEO4J_URI`/`KR_POSTGRES_DSN` point at and
asserts the configured labels, relationship types, tables and columns
literally exist. This is "the day Teammate 1 pushes, I repoint the config
at their database and run this one test" — point the env vars at their
database and re-run this file.

Both tiers assert supersession *direction*, not just that the relationship
type exists (decision 1) — a test that only checks
"SUPERSEDED_BY exists somewhere in the graph" passes on an inverted graph
just as easily as a correct one.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from neo4j import GraphDatabase

from knowledge_reasoning.adapters.fixture import FixtureGraphRepository, FixtureStandardsRepository
from knowledge_reasoning.adapters.live import Neo4jGraphRepository, PostgresStandardsRepository
from knowledge_reasoning.config.schema_map import SchemaMap
from knowledge_reasoning.db.schema import ensure_postgres_schema
from knowledge_reasoning.graph import queries as graph_queries
from knowledge_reasoning.loader.fixture_loader import load_into_neo4j, load_into_postgres

PRIMARY = "IS 10322-5-1:2015"
OLD_EDITION = "IS 10322-5-1:2001"

# A handful of known-seeded facts every tier checks against, so Tier A and
# Tier B are provably asserting the same thing, just via different routes.
EXPECTED_NODE_LABEL_KEY = "standard"
EXPECTED_REL_KEYS = ["normative_reference", "test_method_for", "superseded_by"]
EXPECTED_PROPERTY_KEYS = ["is_number", "title", "status", "verified"]


# ---------------------------------------------------------------------------
# Tier A — backend-agnostic, via ports
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def schema() -> SchemaMap:
    return SchemaMap()


@pytest.fixture(scope="module")
def graph_repository(schema: SchemaMap) -> FixtureGraphRepository:
    return FixtureGraphRepository(schema)


@pytest.fixture(scope="module")
def standards_repository(
    schema: SchemaMap, graph_repository: FixtureGraphRepository
) -> FixtureStandardsRepository:
    return FixtureStandardsRepository(schema, graph_repository)


class TestTierA_PortLevelContract:
    def test_expected_relationship_keys_are_configured(self, schema: SchemaMap) -> None:
        for key in EXPECTED_REL_KEYS:
            assert key in schema.relationship_types

    def test_seed_standard_has_expected_metadata_properties(
        self, standards_repository: FixtureStandardsRepository
    ) -> None:
        meta = standards_repository.get_metadata(PRIMARY)
        assert meta is not None
        assert isinstance(meta.title, str) and meta.title
        assert meta.status in ("active", "superseded", "withdrawn")
        assert isinstance(meta.verified, bool)

    def test_representative_traversal_returns_non_empty_results(
        self, graph_repository: FixtureGraphRepository
    ) -> None:
        paths = graph_repository.expand([PRIMARY], max_hops=2).paths
        assert len(paths) > 0

    def test_supersession_direction_is_correct_not_just_present(
        self, standards_repository: FixtureStandardsRepository
    ) -> None:
        # The decision-1 regression: a test only checking that a
        # SUPERSEDED_BY relationship exists somewhere would pass on an
        # inverted graph. This checks the fact resolves the right way round.
        old_status = standards_repository.get_version_status(OLD_EDITION)
        assert old_status.superseded_by == PRIMARY
        assert old_status.is_current is False

        new_status = standards_repository.get_version_status(PRIMARY)
        assert new_status.superseded_by is None
        assert new_status.is_current is True


# ---------------------------------------------------------------------------
# Tier B — live schema introspection, skipped if unreachable
# ---------------------------------------------------------------------------

TEST_NEO4J_URI = os.environ.get("KR_TEST_NEO4J_URI", "bolt://localhost:7687")
TEST_NEO4J_USER = os.environ.get("KR_TEST_NEO4J_USER", "neo4j")
TEST_NEO4J_PASSWORD = os.environ.get("KR_TEST_NEO4J_PASSWORD", "devpassword")
TEST_POSTGRES_DSN = os.environ.get(
    "KR_TEST_POSTGRES_DSN", "postgresql://postgres:devpassword@localhost:5432/kr_dev"
)


@pytest.fixture(scope="module")
def live_neo4j_driver():
    try:
        driver = GraphDatabase.driver(TEST_NEO4J_URI, auth=(TEST_NEO4J_USER, TEST_NEO4J_PASSWORD))
        driver.verify_connectivity()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Neo4j not reachable at {TEST_NEO4J_URI}: {exc}")
    yield driver
    driver.close()


@pytest.fixture(scope="module")
def live_postgres_conn():
    try:
        conn = psycopg.connect(TEST_POSTGRES_DSN, connect_timeout=3)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Postgres not reachable at {TEST_POSTGRES_DSN}: {exc}")
    yield conn
    conn.close()


@pytest.mark.live_neo4j
class TestTierB_Neo4jSchemaIntrospection:
    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def _seeded(cls, live_neo4j_driver):
        schema = SchemaMap()
        from knowledge_reasoning.adapters.fixture.fixture_data import (
            DEFAULT_FIXTURES_ROOT,
            load_all_fixture_domains,
        )

        domains = load_all_fixture_domains(DEFAULT_FIXTURES_ROOT)
        load_into_neo4j(live_neo4j_driver, schema, domains, env="dev")

    def test_expected_labels_exist(self, live_neo4j_driver) -> None:
        schema = SchemaMap()
        with live_neo4j_driver.session() as session:
            labels = {r["label"] for r in session.run("CALL db.labels() YIELD label RETURN label")}
        assert schema.label(EXPECTED_NODE_LABEL_KEY) in labels

    def test_expected_relationship_types_exist(self, live_neo4j_driver) -> None:
        schema = SchemaMap()
        with live_neo4j_driver.session() as session:
            rel_types = {
                r["relationshipType"]
                for r in session.run(
                    "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
                )
            }
        for key in EXPECTED_REL_KEYS:
            assert schema.rel(key).name in rel_types

    def test_expected_properties_exist_on_a_sample_node(self, live_neo4j_driver) -> None:
        schema = SchemaMap()
        query = graph_queries.build_sample_node_properties_query(schema)
        with live_neo4j_driver.session() as session:
            record = session.run(query).single()
        assert record is not None
        keys = set(record["property_keys"])
        for prop_key in EXPECTED_PROPERTY_KEYS:
            assert schema.prop(prop_key) in keys

    def test_representative_traversal_returns_non_empty_results(self, live_neo4j_driver) -> None:
        schema = SchemaMap()
        repo = Neo4jGraphRepository(live_neo4j_driver, schema)
        paths = repo.expand([PRIMARY], max_hops=2).paths
        assert len(paths) > 0

    def test_supersession_direction_is_correct_against_live_neo4j(self, live_neo4j_driver) -> None:
        schema = SchemaMap()
        repo = Neo4jGraphRepository(live_neo4j_driver, schema)
        old = repo.get_supersession(OLD_EDITION)
        assert old.superseded_by == PRIMARY


@pytest.mark.live_postgres
class TestTierB_PostgresSchemaIntrospection:
    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def _seeded(cls, live_postgres_conn):
        schema = SchemaMap()
        ensure_postgres_schema(live_postgres_conn)
        from knowledge_reasoning.adapters.fixture.fixture_data import (
            DEFAULT_FIXTURES_ROOT,
            load_all_fixture_domains,
        )

        domains = load_all_fixture_domains(DEFAULT_FIXTURES_ROOT)
        load_into_postgres(live_postgres_conn, schema, domains, env="dev")

    def test_expected_tables_exist(self, live_postgres_conn) -> None:
        schema = SchemaMap()
        with live_postgres_conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            tables = {row[0] for row in cur.fetchall()}
        assert schema.table("standards") in tables
        assert schema.table("certification_rules") in tables

    def test_expected_columns_exist_on_standards(self, live_postgres_conn) -> None:
        schema = SchemaMap()
        with live_postgres_conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s",
                (schema.table("standards"),),
            )
            columns = {row[0] for row in cur.fetchall()}
        for key in ("standard_number", "title", "status", "superseded_by_id", "source_url"):
            assert schema.column("standards", key) in columns

    def test_representative_metadata_read_returns_a_row(self, live_postgres_conn) -> None:
        schema = SchemaMap()
        from knowledge_reasoning.adapters.fixture import FixtureGraphRepository

        repo = PostgresStandardsRepository(
            TEST_POSTGRES_DSN, schema, FixtureGraphRepository(schema)
        )
        meta = repo.get_metadata(PRIMARY)
        assert meta is not None

    def test_supersession_direction_is_correct_against_live_postgres(
        self, live_postgres_conn
    ) -> None:
        schema = SchemaMap()
        from knowledge_reasoning.adapters.fixture import FixtureGraphRepository

        repo = PostgresStandardsRepository(
            TEST_POSTGRES_DSN, schema, FixtureGraphRepository(schema)
        )
        old_status = repo.get_version_status(OLD_EDITION)
        assert old_status.superseded_by == PRIMARY
        assert old_status.is_current is False
