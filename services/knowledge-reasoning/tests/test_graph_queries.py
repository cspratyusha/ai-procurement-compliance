from knowledge_reasoning.config.schema_map import RelSpec, SchemaMap
from knowledge_reasoning.graph import queries


def test_expand_one_hop_respects_configured_direction() -> None:
    schema = SchemaMap()
    cypher = queries.build_expand_one_hop_query(
        schema, ["normative_reference", "test_method_for"]
    )
    # outgoing relationship: seed on the left of the arrow
    assert "(s)-[:NORMATIVE_REFERENCE]->(t)" in cypher
    # incoming relationship: seed on the right of the arrow
    assert "(s)<-[:TEST_METHOD_FOR]-(t)" in cypher
    assert "$seeds" in cypher


def test_supersession_query_reads_successor_outgoing_and_predecessor_incoming() -> None:
    schema = SchemaMap()
    cypher = queries.build_supersession_query(schema)
    assert "(s)-[:SUPERSEDED_BY]->(succ)" in cypher
    assert "(s)<-[:SUPERSEDED_BY]-(pred)" in cypher


def test_supersession_query_direction_flips_with_config_override() -> None:
    schema = SchemaMap(
        relationship_types={
            **SchemaMap().relationship_types,
            "superseded_by": RelSpec("SUPERSEDED_BY", "incoming"),
        }
    )
    cypher = queries.build_supersession_query(schema)
    # A reconfigured direction must produce the opposite pattern, proving
    # the query builder actually reads the config rather than hardcoding it.
    assert "(s)<-[:SUPERSEDED_BY]-(succ)" in cypher
    assert "(s)-[:SUPERSEDED_BY]->(pred)" in cypher


def test_curated_overlaps_query_is_symmetric_and_deduped() -> None:
    schema = SchemaMap()
    cypher = queries.build_curated_overlaps_query(schema)
    assert "OVERLAPS_SCOPE_WITH" in cypher
    assert "a.number < b.number" in cypher


def test_merge_relationship_query_never_consults_direction() -> None:
    # Writing always uses the fixture's own explicit from/to, regardless of
    # what direction is configured for reads — see module docstring.
    schema = SchemaMap()
    for rel_key in ("test_method_for", "normative_reference"):
        cypher = queries.build_merge_relationship_query(schema, rel_key)
        assert "(a)-[r:" in cypher
        assert "->(b)" in cypher
        assert "$from_is_number" in cypher and "$to_is_number" in cypher
