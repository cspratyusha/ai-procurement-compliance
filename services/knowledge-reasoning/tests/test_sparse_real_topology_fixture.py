"""Confirms fixtures/sparse_real_topology/ actually has the shape it
claims to — real-corpus-like sparsity, disconnection, and an unmapped
relationship type — so this fixture stays a meaningful stand-in for real
data rather than silently drifting back toward the dense, connected shape
the other two fixtures deliberately use for their own (different) edge
cases.
"""

from __future__ import annotations

from pathlib import Path

from contracts.cluster import EdgeType
from knowledge_reasoning.adapters.fixture.fixture_data import load_fixture_domain
from knowledge_reasoning.adapters.fixture.fixture_graph_repository import FixtureGraphRepository
from knowledge_reasoning.config.schema_map import SchemaMap

DOMAIN_DIR = Path(__file__).parent.parent / "fixtures" / "sparse_real_topology"


def test_edge_density_is_realistically_sparse() -> None:
    domain = load_fixture_domain(DOMAIN_DIR)
    # belongs_to edges are category bookkeeping, not graph-relationship
    # density — exclude them from the same "edges/node" measure Stage C
    # used, or every fixture would look artificially denser than the real
    # corpus it's meant to mirror.
    structural_edges = [e for e in domain.edges if e.type != "belongs_to"]
    density = len(structural_edges) / len(domain.nodes)
    assert density < 1.0, f"expected sparse (<1.0 edges/node), got {density:.2f}"


def test_has_a_fully_isolated_node() -> None:
    domain = load_fixture_domain(DOMAIN_DIR)
    structural_edges = [e for e in domain.edges if e.type != "belongs_to"]
    touched = {e.from_is_number for e in structural_edges} | {
        e.to_value for e in structural_edges
    }
    isolated = [n.is_number for n in domain.nodes if n.is_number not in touched]
    assert "IS 5011:2016" in isolated


def test_majority_of_nodes_have_zero_outgoing_structural_edges() -> None:
    domain = load_fixture_domain(DOMAIN_DIR)
    structural_edges = [e for e in domain.edges if e.type != "belongs_to"]
    has_outgoing = {e.from_is_number for e in structural_edges}
    zero_outdegree = [n for n in domain.nodes if n.is_number not in has_outgoing]
    assert len(zero_outdegree) > len(domain.nodes) / 2


def test_unmapped_type_falls_back_in_a_realistic_looking_fixture() -> None:
    schema = SchemaMap()
    domain = load_fixture_domain(DOMAIN_DIR)
    repo = FixtureGraphRepository(schema, domains=[domain])

    result = repo.expand(["IS 5009:1990"], max_hops=1)
    assert len(result.paths) == 1
    assert result.paths[0].role == EdgeType.RELATED_UNCLASSIFIED
    assert result.paths[0].target == "IS 5010:2012"
    assert result.unmapped_edge_types == {"material_grade_variant": 1}


def test_richest_node_still_reflects_real_corpus_scale() -> None:
    # The real corpus's richest node (IS 2062:2011) has 3 structural edges
    # total. This fixture's richest node should be in the same ballpark,
    # not a hub — that edge case lives in street_lighting/ on purpose.
    schema = SchemaMap()
    domain = load_fixture_domain(DOMAIN_DIR)
    repo = FixtureGraphRepository(schema, domains=[domain])

    result = repo.expand(["IS 5001:2015"], max_hops=1)
    assert len(result.paths) <= 4
