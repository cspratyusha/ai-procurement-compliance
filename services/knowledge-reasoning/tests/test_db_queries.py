from knowledge_reasoning.config.schema_map import SchemaMap
from knowledge_reasoning.db import queries


def test_get_standard_query_uses_configured_table_and_column_names() -> None:
    schema = SchemaMap()
    sql = queries.build_get_standard_query(schema)
    assert "FROM standards s" in sql
    assert "%(is_number)s" in sql
    # Flat category column, no join — see module docstring.
    assert "s.category AS category" in sql
    assert "JOIN" not in sql


def test_get_standard_query_reflects_custom_table_names() -> None:
    schema = SchemaMap(table_names={**SchemaMap().table_names, "standards": "is_standards"})
    sql = queries.build_get_standard_query(schema)
    assert "FROM is_standards s" in sql
    assert "FROM standards s" not in sql


def test_certification_rules_query_is_flat_no_join() -> None:
    schema = SchemaMap()
    sql = queries.build_get_certification_rules_query(schema)
    assert "%(category)s" in sql
    assert "certification_rules" in sql
    assert "JOIN" not in sql


def test_version_row_query_self_joins_within_standards_table_only() -> None:
    schema = SchemaMap()
    sql = queries.build_get_version_row_query(schema)
    assert "s.superseded_by_id = succ.id" in sql


def test_amendments_query_joins_correctly_scoped_columns() -> None:
    schema = SchemaMap()
    sql = queries.build_get_amendments_query(schema)
    # amendments.standard_id (FK) vs standards.id (PK) — the exact collision
    # that forced column_names to become table-scoped.
    assert "a.standard_id = s.id" in sql


def test_upsert_standard_query_is_idempotent_on_conflict() -> None:
    schema = SchemaMap()
    sql = queries.build_upsert_standard_query(schema)
    assert "ON CONFLICT" in sql
    assert "DO UPDATE SET" in sql


def test_column_lookup_is_table_scoped_and_disambiguates_standard_id() -> None:
    schema = SchemaMap()
    assert schema.column("standards", "id") == "id"
    assert schema.column("amendments", "standard_id") == "standard_id"
