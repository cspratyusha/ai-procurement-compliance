import pytest

from contracts.cluster import EdgeType
from knowledge_reasoning.adapters.fixture.fixture_graph_repository import (
    FixtureGraphRepository,
)
from knowledge_reasoning.adapters.fixture.fixture_retrieval_port import (
    FixtureRetrievalPort,
    UnknownMockQueryError,
)
from knowledge_reasoning.adapters.fixture.fixture_standards_repository import (
    FixtureStandardsRepository,
)
from knowledge_reasoning.config.schema_map import SchemaMap

PRIMARY = "IS 10322-5-1:2015"
OLD_EDITION = "IS 10322-5-1:2001"
GENERAL_SAFETY = "IS 10322-1:2014"
IP_CODE_HUB = "IS 12063:1987"
LED_MODULE_SAFETY = "IS 16107-1:2018"
TEST_METHOD = "IS 16106:2015"
WITHDRAWN = "IS 9900:1981"
DANGLING_TARGET = "IS 99999:1999"
OVERLAP_PARTNER = "IS 9974:1981"
EDGE_ONLY_CATEGORY_NODE = "IS 8623-1:1993"


@pytest.fixture(scope="module")
def schema() -> SchemaMap:
    return SchemaMap()


@pytest.fixture(scope="module")
def graph_repo(schema: SchemaMap) -> FixtureGraphRepository:
    return FixtureGraphRepository(schema)


@pytest.fixture(scope="module")
def standards_repo(
    schema: SchemaMap, graph_repo: FixtureGraphRepository
) -> FixtureStandardsRepository:
    return FixtureStandardsRepository(schema, graph_repo)


def test_expand_reaches_installation_and_material_standards_two_hops(
    graph_repo: FixtureGraphRepository,
) -> None:
    # Phase 1 acceptance: "the street lighting query returns the earthing
    # and galvanizing standards in the allied set with correct paths."
    paths = graph_repo.expand([PRIMARY], max_hops=2).paths
    by_target = {p.target: p for p in paths}

    assert "IS 3043:2018" in by_target  # earthing, 1 hop (safety_requirement_for)
    assert by_target["IS 3043:2018"].role == EdgeType.SAFETY_REQUIREMENT_FOR
    assert by_target["IS 3043:2018"].path == [PRIMARY, "IS 3043:2018"]

    assert "IS 2629:1985" in by_target  # galvanizing, 2 hops via the pole standard
    assert by_target["IS 2629:1985"].hop_distance == 2
    assert by_target["IS 2629:1985"].path[0] == PRIMARY
    assert by_target["IS 2629:1985"].path[-1] == "IS 2629:1985"


def test_expand_respects_incoming_direction_for_test_method_for(
    graph_repo: FixtureGraphRepository,
) -> None:
    # IS 16106 -[:TEST_METHOD_FOR]-> IS 10322-5-1 (test-method -> product).
    # From the product's perspective this is an *incoming* edge, so a
    # correctly-directioned expand() must still surface it.
    paths = graph_repo.expand([PRIMARY], max_hops=1).paths
    matches = [p for p in paths if p.target == TEST_METHOD]
    assert len(matches) == 1
    assert matches[0].role == EdgeType.TEST_METHOD_FOR


def test_expand_cycle_does_not_hang_and_visits_each_node_once(
    graph_repo: FixtureGraphRepository,
) -> None:
    # IS 16107-1 <-> IS 16106 is a synthetic 2-cycle (both normative_reference).
    paths = graph_repo.expand([LED_MODULE_SAFETY], max_hops=5).paths
    targets = [p.target for p in paths]
    assert targets.count(TEST_METHOD) <= 1  # visited once, not looped forever


def test_expand_dangling_reference_does_not_crash(
    graph_repo: FixtureGraphRepository,
) -> None:
    # IS 1944-1 -> IS 99999:1999 (not a node in the fixture at all).
    paths = graph_repo.expand(["IS 1944-1:1970"], max_hops=2).paths
    # Should not raise, and the dangling target is still recorded...
    targets = [p.target for p in paths]
    assert DANGLING_TARGET in targets
    # ...but expanding *from* it (hop 2) yields nothing further, no crash.


def test_expand_result_stays_under_truncation_ceiling(
    graph_repo: FixtureGraphRepository,
) -> None:
    # Phase 1 does not implement the Phase 2 result cap yet, but the fixture
    # itself is small enough that an honest 2-hop expansion from the primary
    # street lighting standard should already land well under ~25 members —
    # a smoke check that the graph isn't accidentally over-connected.
    paths = graph_repo.expand([PRIMARY], max_hops=2).paths
    assert len({p.target for p in paths}) < 25


def test_supersession_direction_is_resolved_correctly() -> None:
    # Decision 1's regression test: a test that only checked the
    # relationship type exists would pass on an inverted graph. This checks
    # the actual old->new fact is resolved the right way round.
    schema = SchemaMap()
    graph_repo = FixtureGraphRepository(schema)

    old = graph_repo.get_supersession(OLD_EDITION)
    assert old.superseded_by == PRIMARY
    assert old.supersedes == []

    new = graph_repo.get_supersession(PRIMARY)
    assert new.superseded_by is None
    assert OLD_EDITION in new.supersedes


def test_supersession_direction_inverts_if_schema_map_direction_is_flipped() -> None:
    # Proves the fixture repository actually reads RelSpec.direction rather
    # than hardcoding old->new — the exact failure mode decision 1 warns
    # about (a swapped name silently inverting traversal).
    from knowledge_reasoning.config.schema_map import RelSpec

    flipped = SchemaMap(
        relationship_types={
            **SchemaMap().relationship_types,
            "superseded_by": RelSpec("SUPERSEDED_BY", "incoming"),
        }
    )
    graph_repo = FixtureGraphRepository(flipped)
    old = graph_repo.get_supersession(OLD_EDITION)
    # With direction inverted, the fixture's old->new edge now reads as
    # "old is superseded_by nothing" and shows the new edition as a
    # predecessor instead — the wrong-way-round result decision 1 warns of.
    assert old.superseded_by is None
    assert PRIMARY in old.supersedes


def test_withdrawn_standard_is_flagged(
    standards_repo: FixtureStandardsRepository,
) -> None:
    status = standards_repo.get_version_status(WITHDRAWN)
    assert status.withdrawn is True
    assert status.superseded_by is None


def test_current_edition_has_amendments(
    standards_repo: FixtureStandardsRepository,
) -> None:
    status = standards_repo.get_version_status(PRIMARY)
    assert status.is_current is True
    assert len(status.amendments) == 2
    assert [a.amendment_number for a in status.amendments] == ["A1", "A2"]


def test_data_verified_is_false_for_placeholder_fixture(
    standards_repo: FixtureStandardsRepository,
) -> None:
    status = standards_repo.get_version_status(PRIMARY)
    assert status.data_verified is False


def test_curated_overlap_is_found_with_provenance(
    graph_repo: FixtureGraphRepository,
) -> None:
    overlaps = graph_repo.get_curated_overlaps([PRIMARY, OVERLAP_PARTNER])
    assert len(overlaps) == 1
    assert {overlaps[0].is_a, overlaps[0].is_b} == {PRIMARY, OVERLAP_PARTNER}
    assert overlaps[0].overlap_score == pytest.approx(0.72)


def test_category_property_strategy_is_primary_by_default(
    standards_repo: FixtureStandardsRepository,
) -> None:
    assert standards_repo.get_product_category(PRIMARY) == "LED Street Lighting"


def test_category_falls_back_to_edge_when_property_missing(
    standards_repo: FixtureStandardsRepository,
) -> None:
    # IS 8623-1:1993 has category: null in nodes.yaml, only a belongs_to
    # edge in edges.yaml — decision 4's fallback path.
    assert standards_repo.get_product_category(EDGE_ONLY_CATEGORY_NODE) == "Electrical Installation"


def test_certification_rules_unmapped_category_returns_empty_not_error(
    standards_repo: FixtureStandardsRepository,
) -> None:
    # "Structural & Materials" has no certification_rules.yaml entry at all
    # — the repository returns [], and it's the Phase 3 mapper's job to
    # turn "no rules found" into scheme: UNKNOWN, never NONE.
    assert standards_repo.get_certification_rules("Structural & Materials") == []


def test_certification_rules_mapped_category_returns_isi_rule(
    standards_repo: FixtureStandardsRepository,
) -> None:
    rules = standards_repo.get_certification_rules("LED Street Lighting")
    assert len(rules) == 1
    assert rules[0].scheme == "ISI"
    assert rules[0].mandatory is True


def test_mock_retrieval_returns_valid_results_for_fixed_queries() -> None:
    port = FixtureRetrievalPort()
    result = port.retrieve("LED street light", top_k=5)
    assert result.candidates[0].is_number == PRIMARY
    assert result.original_language == "en-IN"


def test_mock_retrieval_orphan_query_is_low_confidence() -> None:
    port = FixtureRetrievalPort()
    result = port.retrieve("quantum flux capacitor mounting bracket", top_k=5)
    assert all(c.score < 0.5 for c in result.candidates)


def test_mock_retrieval_unknown_query_raises_not_silently_empty() -> None:
    port = FixtureRetrievalPort()
    with pytest.raises(UnknownMockQueryError):
        port.retrieve("something never seeded in the fixture", top_k=5)


def test_unmapped_relationship_type_falls_back_not_dropped() -> None:
    # Integration decision 3: an unrecognised type is a lower-confidence,
    # distinctly-labelled member, never silently invisible.
    from knowledge_reasoning.adapters.fixture.fixture_data import (
        FixtureDomain,
        FixtureEdge,
        FixtureNode,
    )

    nodes = [
        FixtureNode(
            is_number="IS 1:2020", title="A", scope_text=None, status="active",
            edition=None, category=None, verified=False,
        ),
        FixtureNode(
            is_number="IS 2:2020", title="B", scope_text=None, status="active",
            edition=None, category=None, verified=False,
        ),
    ]
    edges = [
        FixtureEdge(
            type="totally_novel_relationship_xyz",
            from_is_number="IS 1:2020",
            to_value="IS 2:2020",
            verified=False,
        )
    ]
    domain = FixtureDomain(name="synthetic", nodes=nodes, edges=edges)
    repo = FixtureGraphRepository(SchemaMap(), domains=[domain])

    result = repo.expand(["IS 1:2020"], max_hops=1)
    assert len(result.paths) == 1
    assert result.paths[0].role == EdgeType.RELATED_UNCLASSIFIED
    assert result.paths[0].target == "IS 2:2020"
    assert result.unmapped_edge_types == {"totally_novel_relationship_xyz": 1}


def test_recognised_non_membership_type_is_neither_traversed_nor_unmapped() -> None:
    # superseded_by is a known schema_map key but not a cluster-membership
    # role — it must be excluded from expand() (read via get_supersession
    # instead), not counted as unmapped just because it's not in
    # _rel_keys.
    from knowledge_reasoning.adapters.fixture.fixture_data import (
        FixtureDomain,
        FixtureEdge,
        FixtureNode,
    )

    nodes = [
        FixtureNode(
            is_number="IS 1:2020", title="A", scope_text=None, status="superseded",
            edition=None, category=None, verified=False,
        ),
        FixtureNode(
            is_number="IS 2:2020", title="B", scope_text=None, status="active",
            edition=None, category=None, verified=False,
        ),
    ]
    edges = [
        FixtureEdge(
            type="superseded_by", from_is_number="IS 1:2020", to_value="IS 2:2020", verified=False
        )
    ]
    domain = FixtureDomain(name="synthetic", nodes=nodes, edges=edges)
    repo = FixtureGraphRepository(SchemaMap(), domains=[domain])

    result = repo.expand(["IS 1:2020"], max_hops=1)
    assert result.paths == []
    assert result.unmapped_edge_types == {}


def test_all_real_fixture_relationship_types_are_mapped() -> None:
    # Regression guard for the reporting CLI's own claim: run
    # `python -m knowledge_reasoning.loader.report_relationship_types` any
    # time this fails to see exactly which type changed.
    #
    # material_grade_variant (fixtures/sparse_real_topology/) is a
    # deliberate, permanent exception: it exists specifically to exercise
    # the fallback bucket (decision 3/Stage E.4) in a realistic-shaped
    # fixture — see test_unmapped_type_falls_back_in_a_realistic_looking_fixture
    # in test_sparse_real_topology_fixture.py. Any OTHER unmapped type is
    # still a real regression this test must catch.
    from knowledge_reasoning.loader.report_relationship_types import (
        fixture_relationship_type_counts,
        known_keys,
    )

    schema = SchemaMap()
    counts = fixture_relationship_type_counts()
    unmapped = set(counts) - known_keys(schema) - {"material_grade_variant"}
    assert not unmapped, f"unmapped relationship types in fixtures/: {unmapped}"
