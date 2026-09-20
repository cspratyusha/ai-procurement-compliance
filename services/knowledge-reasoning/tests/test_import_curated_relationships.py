"""Curation importer, run against a real Postgres seeded with the usual
fixture data — proves it loads a relationships.json-shaped file end to
end, skips dangling references instead of crashing, writes (rather than
drops) unmapped types, and is idempotent on rerun.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
import pytest

from knowledge_reasoning.adapters.fixture.fixture_data import (
    DEFAULT_FIXTURES_ROOT,
    load_all_fixture_domains,
)
from contracts.cluster import EdgeType
from knowledge_reasoning.adapters.live import PostgresGraphRepository
from knowledge_reasoning.config.schema_map import SchemaMap
from knowledge_reasoning.db.schema import ensure_postgres_schema
from knowledge_reasoning.loader.fixture_loader import load_into_postgres
from knowledge_reasoning.loader.import_curated_relationships import (
    CurationImportError,
    import_curated_relationships,
    load_curated_relationships_file,
)

TEST_POSTGRES_DSN = os.environ.get(
    "KR_TEST_POSTGRES_DSN", "postgresql://postgres:devpassword@localhost:5432/kr_dev"
)

pytestmark = pytest.mark.live_postgres

PRIMARY = "IS 10322-5-1:2015"
IP_CODE_HUB = "IS 12063:1987"
# A cross-domain pair (street_lighting -> reinforcement_steel) with no
# pre-existing edge in the fixture data — so importing a relationship
# between them is a genuine addition, not a no-op duplicate of something
# already there.
UNRELATED_TARGET = "IS 1786:2008"


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
        conn.close()
        raise
    yield conn
    # kr_dev is a shared live database across the whole test *session*, not
    # just this module — test_postgres_graph_repository.py's fixture/Postgres
    # parity tests assume expand(PRIMARY) is identical between backends,
    # which only holds if this module leaves the shared DB exactly as the
    # fixture loader left it. Delete precisely the extra rows the tests
    # above add (never anything the YAML fixtures themselves wrote) so a
    # later-alphabetical module never sees them.
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM standard_relationships WHERE "
            "(source_id, target_id, type) IN ((%s, %s, %s), (%s, %s, %s))",
            (
                PRIMARY, UNRELATED_TARGET, "NORMATIVE_REFERENCE",
                IP_CODE_HUB, UNRELATED_TARGET, "MATERIAL_GRADE_VARIANT",
            ),
        )
    conn.commit()
    conn.close()


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "relationships.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def test_valid_curated_file_loads_and_is_readable_via_the_graph_repository(
    pg_conn, schema: SchemaMap, tmp_path: Path
) -> None:
    # This codebase's own fixture loader uses the IS number as
    # standards.id (see fixture_loader.load_into_postgres), so that's what
    # a curated file's source_id/target_id resolve to here too — against
    # Teammate 1's real corpus these would be their std_NNN-style ids
    # instead, per the module docstring.
    rows = [{"source_id": PRIMARY, "target_id": UNRELATED_TARGET, "type": "NORMATIVE_REFERENCE"}]
    path = _write(tmp_path, rows)

    parsed = load_curated_relationships_file(path)
    report = import_curated_relationships(pg_conn, schema, parsed)

    assert report.rows_read == 1
    assert report.rows_written == 1
    assert report.rows_dropped_dangling == []
    assert report.unmapped_types_seen == {}

    repo = PostgresGraphRepository(TEST_POSTGRES_DSN, schema)
    result = repo.expand([PRIMARY], max_hops=1)
    assert any(
        p.target == UNRELATED_TARGET and p.role == EdgeType.NORMATIVE_REFERENCE
        for p in result.paths
    )


def test_rerun_is_idempotent(pg_conn, schema: SchemaMap, tmp_path: Path) -> None:
    rows = [{"source_id": PRIMARY, "target_id": UNRELATED_TARGET, "type": "NORMATIVE_REFERENCE"}]
    path = _write(tmp_path, rows)
    parsed = load_curated_relationships_file(path)

    import_curated_relationships(pg_conn, schema, parsed)
    report = import_curated_relationships(pg_conn, schema, parsed)

    assert report.rows_written == 1  # ON CONFLICT DO NOTHING, no error either time


def test_dangling_reference_is_skipped_and_reported_not_crashed(
    pg_conn, schema: SchemaMap, tmp_path: Path
) -> None:
    rows = [
        {"source_id": PRIMARY, "target_id": "IS 999999:1999", "type": "NORMATIVE_REFERENCE"}
    ]
    path = _write(tmp_path, rows)
    parsed = load_curated_relationships_file(path)

    report = import_curated_relationships(pg_conn, schema, parsed)

    assert report.rows_written == 0
    assert report.rows_dropped_dangling == [
        ("NORMATIVE_REFERENCE", PRIMARY, "IS 999999:1999")
    ]


def test_unmapped_type_is_written_not_dropped(
    pg_conn, schema: SchemaMap, tmp_path: Path
) -> None:
    rows = [
        {"source_id": IP_CODE_HUB, "target_id": UNRELATED_TARGET, "type": "MATERIAL_GRADE_VARIANT"}
    ]
    path = _write(tmp_path, rows)
    parsed = load_curated_relationships_file(path)

    report = import_curated_relationships(pg_conn, schema, parsed)

    assert report.rows_written == 1
    assert report.unmapped_types_seen == {"MATERIAL_GRADE_VARIANT": 1}

    repo = PostgresGraphRepository(TEST_POSTGRES_DSN, schema)
    result = repo.expand([IP_CODE_HUB], max_hops=1)
    assert any(
        p.target == UNRELATED_TARGET and p.role == EdgeType.RELATED_UNCLASSIFIED
        for p in result.paths
    )
    assert result.unmapped_edge_types.get("MATERIAL_GRADE_VARIANT") == 1


def test_malformed_top_level_raises(tmp_path: Path) -> None:
    path = tmp_path / "relationships.json"
    path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    with pytest.raises(CurationImportError):
        load_curated_relationships_file(path)


def test_row_missing_required_field_raises(tmp_path: Path) -> None:
    path = tmp_path / "relationships.json"
    path.write_text(json.dumps([{"source_id": "a", "target_id": "b"}]), encoding="utf-8")
    with pytest.raises(CurationImportError):
        load_curated_relationships_file(path)
