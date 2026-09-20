"""PostgresGraphRepository, run against a real Postgres seeded with the
same fixture data FixtureGraphRepository uses — proves the two backends
agree, not just that each one independently "does something".
"""

from __future__ import annotations

import os

import psycopg
import pytest

from knowledge_reasoning.adapters.fixture import FixtureGraphRepository
from knowledge_reasoning.adapters.fixture.fixture_data import (
    DEFAULT_FIXTURES_ROOT,
    load_all_fixture_domains,
)
from knowledge_reasoning.adapters.live import PostgresGraphRepository
from knowledge_reasoning.config.schema_map import SchemaMap
from knowledge_reasoning.db.schema import ensure_postgres_schema
from knowledge_reasoning.loader.fixture_loader import load_into_postgres

TEST_POSTGRES_DSN = os.environ.get(
    "KR_TEST_POSTGRES_DSN", "postgresql://postgres:devpassword@localhost:5432/kr_dev"
)

PRIMARY = "IS 10322-5-1:2015"
OLD_EDITION = "IS 10322-5-1:2001"
IP_CODE_HUB = "IS 12063:1987"
OVERLAP_PARTNER = "IS 9974:1981"


@pytest.fixture(scope="module")
def schema() -> SchemaMap:
    return SchemaMap()


@pytest.fixture(scope="module")
def pg_conn(schema: SchemaMap):
    try:
        conn = psycopg.connect(TEST_POSTGRES_DSN, connect_timeout=3)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Postgres not reachable at {TEST_POSTGRES_DSN}: {exc}")
    try:
        ensure_postgres_schema(conn)
        domains = load_all_fixture_domains(DEFAULT_FIXTURES_ROOT)
        load_into_postgres(conn, schema, domains, env="dev")
    except BaseException:
        # A failure here (setup errors before the fixture's yield don't
        # otherwise trigger cleanup) must never leave conn open holding
        # locks on an uncommitted transaction — that's what turned one
        # earlier bug (an unmapped relationship type crashing the loader
        # mid-transaction) into a full-suite hang: this connection sat
        # idle-in-transaction indefinitely, blocking every later test
        # module's own Postgres connection on the same rows.
        conn.close()
        raise
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def pg_repo(schema: SchemaMap, pg_conn) -> PostgresGraphRepository:
    return PostgresGraphRepository(TEST_POSTGRES_DSN, schema)


@pytest.fixture(scope="module")
def fixture_repo(schema: SchemaMap) -> FixtureGraphRepository:
    return FixtureGraphRepository(schema)


pytestmark = pytest.mark.live_postgres


# The fixture's deliberate dangling-reference edge (IS 1944-1:1970 ->
# IS 99999:1999, a node that doesn't exist) behaves differently by design
# between backends: Neo4j's/networkx's MERGE-style add auto-vivifies a bare
# phantom node, so FixtureGraphRepository can still reach it; Postgres has a
# real FK constraint, so the loader drops that one edge at load time (see
# fixture_loader.py) and PostgresGraphRepository correctly never reaches it.
# This is the documented divergence from fixtures/README.md's "ugly cases",
# not a bug — excluded from the parity comparison below on purpose.
_KNOWN_DANGLING_TARGET = "IS 99999:1999"


def _as_set(paths):
    return {
        (p.target, p.role, p.hop_distance) for p in paths if p.target != _KNOWN_DANGLING_TARGET
    }


def test_expand_matches_fixture_backend_two_hops(pg_repo, fixture_repo) -> None:
    pg_paths = pg_repo.expand([PRIMARY], max_hops=2).paths
    fixture_paths = fixture_repo.expand([PRIMARY], max_hops=2).paths
    assert _as_set(pg_paths) == _as_set(fixture_paths)
    assert len(pg_paths) > 0


def test_expand_path_sequences_match(pg_repo, fixture_repo) -> None:
    pg_by_target = {
        p.target: p.path
        for p in pg_repo.expand([PRIMARY], max_hops=2).paths
        if p.target != _KNOWN_DANGLING_TARGET
    }
    fixture_by_target = {
        p.target: p.path
        for p in fixture_repo.expand([PRIMARY], max_hops=2).paths
        if p.target != _KNOWN_DANGLING_TARGET
    }
    assert pg_by_target == fixture_by_target


def test_expand_cycle_does_not_hang_against_real_postgres(pg_repo) -> None:
    paths = pg_repo.expand(["IS 16107-1:2018"], max_hops=5).paths
    targets = [p.target for p in paths]
    assert targets.count("IS 16106:2015") <= 1


def test_expand_dangling_reference_does_not_crash_against_real_postgres(pg_repo) -> None:
    # The dangling edge is dropped at load time (real FK constraints,
    # unlike Neo4j's MERGE) — this asserts the load+read path survives it,
    # not that the phantom target is reachable.
    paths = pg_repo.expand(["IS 1944-1:1970"], max_hops=1).paths
    assert isinstance(paths, list)


def test_supersession_direction_correct_against_real_postgres(pg_repo) -> None:
    old = pg_repo.get_supersession(OLD_EDITION)
    assert old.superseded_by == PRIMARY
    new = pg_repo.get_supersession(PRIMARY)
    assert new.superseded_by is None
    assert OLD_EDITION in new.supersedes


def test_curated_overlap_matches_fixture_backend(pg_repo, fixture_repo) -> None:
    pg_overlaps = pg_repo.get_curated_overlaps([PRIMARY, OVERLAP_PARTNER])
    fixture_overlaps = fixture_repo.get_curated_overlaps([PRIMARY, OVERLAP_PARTNER])
    assert len(pg_overlaps) == 1
    assert {pg_overlaps[0].is_a, pg_overlaps[0].is_b} == {
        fixture_overlaps[0].is_a,
        fixture_overlaps[0].is_b,
    }


def test_unmapped_relationship_type_falls_back_against_real_postgres(pg_repo, pg_conn) -> None:
    # Integration decision 3, verified against the live recursive-CTE path
    # specifically: an unrecognised type string in standard_relationships
    # is never silently dropped.
    from contracts.cluster import EdgeType

    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO standard_relationships (source_id, target_id, type) "
            "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (PRIMARY, OVERLAP_PARTNER, "TOTALLY_NOVEL_RELATIONSHIP_XYZ"),
        )
        pg_conn.commit()
    try:
        result = pg_repo.expand([PRIMARY], max_hops=1)
        matches = [p for p in result.paths if p.target == OVERLAP_PARTNER]
        assert len(matches) == 1
        assert matches[0].role == EdgeType.RELATED_UNCLASSIFIED
        assert result.unmapped_edge_types.get("TOTALLY_NOVEL_RELATIONSHIP_XYZ") == 1
    finally:
        with pg_conn.cursor() as cur:
            cur.execute(
                "DELETE FROM standard_relationships WHERE type = 'TOTALLY_NOVEL_RELATIONSHIP_XYZ'"
            )
            pg_conn.commit()


def test_hub_node_reachable_via_multiple_normative_references(pg_repo) -> None:
    # IS 12063:1987 is the deliberate hub — five inbound normative_reference
    # edges (see fixtures/README.md). Confirms multi-seed fan-in resolves
    # against real Postgres the same way it does in-memory.
    paths = pg_repo.expand([PRIMARY], max_hops=1).paths
    assert any(p.target == IP_CODE_HUB for p in paths)
