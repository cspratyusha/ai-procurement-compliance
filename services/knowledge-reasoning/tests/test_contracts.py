from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts.cluster import (
    CertificationRequirement,
    ClusterMember,
    EdgeType,
    GraphStats,
    OverlapWarning,
    ValidatedCluster,
    VersionStatus,
)
from contracts.generation import GeneratedResponse, GroundingReport, StandardExplanation
from contracts.retrieval import RetrievalCandidate, RetrievalResult


def _version_status(**overrides) -> VersionStatus:
    defaults = dict(
        current_edition="IS 10322-5-3:2020",
        is_current=True,
        withdrawn=False,
        last_verified=datetime(2024, 1, 1),
        data_verified=False,
    )
    defaults.update(overrides)
    return VersionStatus(**defaults)


def _certification(**overrides) -> CertificationRequirement:
    defaults = dict(scheme="UNKNOWN", mandatory=False)
    defaults.update(overrides)
    return CertificationRequirement(**defaults)


def test_retrieval_candidate_canonicalises_is_number() -> None:
    c = RetrievalCandidate(
        is_number="IS:10322(Pt5/Sec3)",
        title="LED road lighting luminaires",
        score=0.9,
        match_reason="hybrid",
    )
    assert c.is_number == "IS 10322-5-3"


def test_retrieval_candidate_rejects_out_of_range_score() -> None:
    with pytest.raises(ValidationError):
        RetrievalCandidate(
            is_number="IS 456", title="x", score=1.5, match_reason="dense"
        )


def test_retrieval_candidate_rejects_unparseable_is_number() -> None:
    with pytest.raises(ValidationError):
        RetrievalCandidate(
            is_number="not a standard", title="x", score=0.5, match_reason="dense"
        )


def test_retrieval_result_round_trip() -> None:
    result = RetrievalResult(
        query_id=uuid4(),
        normalised_query="led street light",
        original_query="LED street light",
        original_language="en-IN",
        candidates=[
            RetrievalCandidate(
                is_number="IS 10322 Part 5 Section 3",
                title="LED road lighting luminaires",
                score=0.87,
                match_reason="hybrid",
            )
        ],
    )
    dumped = result.model_dump_json()
    reloaded = RetrievalResult.model_validate_json(dumped)
    assert reloaded.candidates[0].is_number == "IS 10322-5-3"


def test_cluster_member_canonicalises_path_and_is_number() -> None:
    member = ClusterMember(
        is_number="IS:10322(Pt5/Sec3)",
        title="LED road lighting luminaires",
        role=EdgeType.NORMATIVE_REFERENCE,
        relevance=0.8,
        path=["IS 10322-1", "IS:10322(Pt5/Sec3)"],
        hop_distance=1,
        version=_version_status(),
        certification=_certification(),
    )
    assert member.is_number == "IS 10322-5-3"
    assert member.path == ["IS 10322-1", "IS 10322-5-3"]


def test_cluster_member_rejects_negative_hop_distance() -> None:
    with pytest.raises(ValidationError):
        ClusterMember(
            is_number="IS 456",
            title="x",
            role=EdgeType.NORMATIVE_REFERENCE,
            relevance=0.5,
            path=["IS 456"],
            hop_distance=-1,
            version=_version_status(),
            certification=_certification(),
        )


def test_certification_requirement_unknown_is_a_valid_scheme() -> None:
    req = _certification(scheme="UNKNOWN")
    assert req.scheme == "UNKNOWN"


def test_overlap_warning_requires_source_provenance() -> None:
    with pytest.raises(ValidationError):
        OverlapWarning(
            is_a="IS 456",
            is_b="IS 457",
            overlap_score=0.6,
            explanation_hint="scope_overlap:clause_4",
        )  # missing `source`

    warning = OverlapWarning(
        is_a="IS 456",
        is_b="IS 457",
        overlap_score=0.6,
        explanation_hint="scope_overlap:clause_4",
        source="computed",
    )
    assert warning.source == "computed"


def test_validated_cluster_confidence_bounds() -> None:
    stats = GraphStats(seeds=["IS 456"], max_hops=2, nodes_visited=3, edges_traversed=2)
    with pytest.raises(ValidationError):
        ValidatedCluster(
            query_id=uuid4(),
            primary=[],
            allied=[],
            orphan=False,
            confidence=1.2,
            graph_stats=stats,
        )


def test_orphan_cluster_shape() -> None:
    stats = GraphStats(seeds=["IS 999999"], max_hops=2, nodes_visited=0, edges_traversed=0)
    cluster = ValidatedCluster(
        query_id=uuid4(),
        primary=[],
        allied=[],
        orphan=True,
        orphan_reason="no candidate cleared the confidence threshold",
        confidence=0.12,
        graph_stats=stats,
    )
    assert cluster.orphan is True
    assert cluster.primary == []


def test_generated_response_grounding_report_canonicalises() -> None:
    response = GeneratedResponse(
        query_id=uuid4(),
        summary="...",
        explanations=[
            StandardExplanation(is_number="IS:10322(Pt5/Sec3)", why_recommended="...")
        ],
        language="en-IN",
        grounding_report=GroundingReport(
            context_is_numbers=["IS 10322-5-3"],
            cited_is_numbers=["IS:10322(Pt5/Sec3)"],
            passed=True,
        ),
    )
    assert response.grounding_report.cited_is_numbers == ["IS 10322-5-3"]
