"""Orphan gate tests, grounded in the real evidence cited in
orphan_gate.py's module docstring: two logged accept-case score sets from
Teammate 2's interaction_logs.jsonl, and the documented "not comparable
across calls" property of their final_score.
"""

from __future__ import annotations

from contracts.cluster import EdgeType
from contracts.retrieval import RetrievalCandidate
from knowledge_reasoning.ports.types import ExpansionResult, GraphPath
from knowledge_reasoning.validation.orphan_gate import (
    OrphanGateConfig,
    evaluate_orphan_gate,
)


def _candidate(is_number: str, score: float) -> RetrievalCandidate:
    return RetrievalCandidate(
        is_number=is_number, title="x", score=score, match_reason="hybrid"
    )


class _FakeGraphRepository:
    """Minimal GraphRepository stand-in: only expand() matters here."""

    def __init__(self, corroborated: bool) -> None:
        self._corroborated = corroborated

    def expand(self, seeds, max_hops):
        if not self._corroborated:
            return ExpansionResult(paths=[])
        return ExpansionResult(
            paths=[
                GraphPath(
                    target="IS 9999:2020",
                    role=EdgeType.NORMATIVE_REFERENCE,
                    path=[seeds[0], "IS 9999:2020"],
                    hop_distance=1,
                )
            ]
        )

    def get_supersession(self, is_number):  # pragma: no cover - unused
        raise NotImplementedError

    def get_curated_overlaps(self, is_numbers):  # pragma: no cover - unused
        raise NotImplementedError

    def get_category_via_edge(self, is_number):  # pragma: no cover - unused
        raise NotImplementedError


# Real logged accept-case scores (Teammate 2's interaction_logs.jsonl,
# integration Stage C) — a genuinely confident match in their real system.
_REAL_CONFIDENT_SCORES = [0.4693, 0.3388, 0.189, 0.1321, 0.0445, 0.01, 0.01, 0.01, 0.01, 0.01]


def test_no_candidates_is_orphan() -> None:
    result = evaluate_orphan_gate([])
    assert result.orphan is True
    assert result.reason == "no_candidates"


def test_real_confident_score_set_is_not_orphan() -> None:
    candidates = [_candidate(f"IS {100 + i}:2020", s) for i, s in enumerate(_REAL_CONFIDENT_SCORES)]
    result = evaluate_orphan_gate(candidates)
    assert result.orphan is False
    assert result.margin is not None and result.margin > 0.13


def test_flat_low_margin_candidates_are_orphan_without_corroboration() -> None:
    # Shape seen in the BM25 nonsense-query smoke test: several
    # near-identical low scores, no real separation.
    candidates = [_candidate("IS 101:2020", 0.31), _candidate("IS 102:2020", 0.29)]
    result = evaluate_orphan_gate(candidates)
    assert result.orphan is True
    assert result.reason == "insufficient_margin"


def test_low_margin_rescued_by_graph_corroboration() -> None:
    candidates = [_candidate("IS 101:2020", 0.31), _candidate("IS 102:2020", 0.29)]
    result = evaluate_orphan_gate(candidates, graph_repository=_FakeGraphRepository(True))
    assert result.orphan is False
    assert result.graph_corroborated is True


def test_single_candidate_with_graph_corroboration_is_not_orphan() -> None:
    result = evaluate_orphan_gate(
        [_candidate("IS 101:2020", 0.9)], graph_repository=_FakeGraphRepository(True)
    )
    assert result.orphan is False


def test_single_candidate_without_corroboration_is_orphan_even_at_high_score() -> None:
    # The central claim this module exists for: a high absolute score
    # alone is not trusted.
    result = evaluate_orphan_gate(
        [_candidate("IS 101:2020", 0.95)], graph_repository=_FakeGraphRepository(False)
    )
    assert result.orphan is True
    assert result.reason == "single_candidate_no_corroboration"


def test_single_candidate_with_no_graph_repository_degrades_to_orphan() -> None:
    # No graph_repository passed at all -> corroboration can't be
    # confirmed -> conservative default, not a crash.
    result = evaluate_orphan_gate([_candidate("IS 101:2020", 0.95)])
    assert result.orphan is True
    assert result.graph_corroborated is None


def test_flat_distribution_flagged_even_with_passing_margin() -> None:
    # Margin between rank 1 and 2 clears the bar, but every other
    # candidate sits in the same tight cluster as rank 2 — genuinely flat
    # overall, not a confident single winner.
    candidates = [
        _candidate("IS 101:2020", 0.40),
        _candidate("IS 102:2020", 0.29),
        _candidate("IS 103:2020", 0.285),
        _candidate("IS 104:2020", 0.28),
        _candidate("IS 105:2020", 0.275),
    ]
    result = evaluate_orphan_gate(candidates)
    assert result.margin is not None and result.margin >= 0.10
    assert result.orphan is True
    assert result.reason == "flat_score_distribution"


def test_absolute_floor_disabled_by_default_does_not_reject_low_but_separated_score() -> None:
    # Central design claim: no fixed absolute cutoff by default, however
    # low the top score, if the margin and shape are confident.
    candidates = [_candidate("IS 101:2020", 0.15), _candidate("IS 102:2020", 0.01)]
    result = evaluate_orphan_gate(candidates)
    assert result.orphan is False


def test_absolute_floor_when_explicitly_enabled_overrides_a_good_margin() -> None:
    candidates = [_candidate("IS 101:2020", 0.15), _candidate("IS 102:2020", 0.01)]
    config = OrphanGateConfig(absolute_floor=0.5)
    result = evaluate_orphan_gate(candidates, config=config)
    assert result.orphan is True
    assert result.reason == "below_absolute_floor"
