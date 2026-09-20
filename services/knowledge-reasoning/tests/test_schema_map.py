from pathlib import Path

import pytest

from knowledge_reasoning.config.schema_map import (
    RelSpec,
    SchemaMap,
    SchemaMapError,
    load_schema_map,
)

REPO_YAML = Path(__file__).parent.parent / "knowledge_reasoning" / "config" / "schema_map.yaml"


def test_default_schema_map_validates_clean() -> None:
    schema = SchemaMap()
    schema.validate()  # must not raise


def test_relspec_rejects_bad_identifier() -> None:
    with pytest.raises(SchemaMapError):
        RelSpec(name="NOT A VALID NAME", direction="outgoing")


def test_relspec_rejects_bad_direction() -> None:
    with pytest.raises(SchemaMapError):
        RelSpec(name="SUPERSEDED_BY", direction="sideways")


def test_relspec_injection_like_value_rejected() -> None:
    # A label/rel-type string gets interpolated directly into Cypher; this
    # must be caught at load time, not discovered as a broken query later.
    with pytest.raises(SchemaMapError):
        RelSpec(name="X]->(n) DETACH DELETE n //", direction="outgoing")


def test_bundled_yaml_matches_python_defaults() -> None:
    # The checked-in schema_map.yaml is meant to be a faithful mirror of the
    # Python defaults (a usable starting template), not a placeholder.
    schema = load_schema_map(REPO_YAML)
    defaults = SchemaMap()
    assert schema.node_labels == defaults.node_labels
    assert schema.relationship_types == defaults.relationship_types
    assert schema.property_names == defaults.property_names
    assert schema.table_names == defaults.table_names
    assert schema.column_names == defaults.column_names
    assert schema.category_strategy == defaults.category_strategy


def test_yaml_override_partial_merge(tmp_path: Path) -> None:
    override = tmp_path / "override.yaml"
    override.write_text(
        """
relationship_types:
  superseded_by:
    name: SUPERSEDED_BY_LEGACY
    direction: incoming
category_strategy: edge
"""
    )
    schema = load_schema_map(override)
    # Overridden key changed...
    assert schema.relationship_types["superseded_by"] == RelSpec(
        "SUPERSEDED_BY_LEGACY", "incoming"
    )
    assert schema.category_strategy == "edge"
    # ...everything else still falls back to defaults.
    assert schema.node_labels == SchemaMap().node_labels
    assert schema.relationship_types["normative_reference"] == RelSpec(
        "NORMATIVE_REFERENCE", "outgoing"
    )


def test_yaml_override_with_malicious_identifier_rejected(tmp_path: Path) -> None:
    override = tmp_path / "override.yaml"
    override.write_text(
        """
node_labels:
  standard: "Standard) DETACH DELETE n //"
"""
    )
    with pytest.raises(SchemaMapError):
        load_schema_map(override)


def test_yaml_override_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(SchemaMapError):
        load_schema_map(tmp_path / "does-not-exist.yaml")


def test_column_names_is_table_scoped_and_resolves_same_concept_two_ways() -> None:
    # The real bug that forced this: standards' own PK is `id`, but
    # amendments' FK pointing at it is `standard_id` — two different real
    # column names for "the standard" in two different tables.
    schema = SchemaMap()
    assert schema.column("standards", "id") == "id"
    assert schema.column("amendments", "standard_id") == "standard_id"


def test_column_names_yaml_override_is_scoped_to_one_table(tmp_path: Path) -> None:
    override = tmp_path / "override.yaml"
    override.write_text(
        """
column_names:
  standards:
    standard_number: legacy_number
"""
    )
    schema = load_schema_map(override)
    assert schema.column("standards", "standard_number") == "legacy_number"
    # Untouched keys in the same table still fall back to defaults...
    assert schema.column("standards", "title") == "title"
    # ...as does every other table entirely.
    assert schema.column("amendments", "standard_id") == "standard_id"


def test_relationship_keys_align_with_edge_type_enum() -> None:
    # Cluster-membership roles in RELATIONSHIP_TYPES must be addressable by
    # EdgeType.value directly (RELATIONSHIP_TYPES[edge_type.value]) — except
    # RELATED_UNCLASSIFIED, which is deliberately never a schema_map key: it's
    # the dynamic fallback role assigned at read time for a relationship type
    # with no configured mapping at all (decision 3), not something anyone
    # configures a name/direction for.
    from contracts.cluster import EdgeType

    schema = SchemaMap()
    for edge_type in EdgeType:
        if edge_type is EdgeType.RELATED_UNCLASSIFIED:
            assert edge_type.value not in schema.relationship_types
            continue
        assert edge_type.value in schema.relationship_types, (
            f"EdgeType.{edge_type.name} has no matching schema_map entry"
        )
