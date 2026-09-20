"""The orphan-query gate: decide whether a set of retrieval candidates
clears enough confidence to return as a recommendation, or should be
flagged as a potential standards-landscape gap instead (brief B6 / the
"orphan" path throughout `Solution_details/`).

This is the first piece of actual Phase 3 business logic built in this
service — everything before it was the repository/adapter/config layer
that logic like this depends on.

Why this isn't an absolute score cutoff
-----------------------------------------
The original design (Phase 1) assumed `RetrievalCandidate.score` was a
calibrated, cross-query-comparable confidence, and would have used a fixed
floor (e.g. "orphan if top score < 0.5"). Integration Stage C found real
evidence against that assumption against Teammate 2's actual retrieval
system:

- `final_score` is explicitly documented in their own code
  (`retrieval/postprocess.py`) as "a relative ranking signal... not a
  calibrated probability... not comparable across separate /retrieve
  calls" — it's rescaled per-response (shift + clamp to [0,1] based on
  that response's own min/max), so the same underlying relevance can
  produce different absolute numbers depending on what else is in the
  batch.
- Their own logged output (`interaction_logs.jsonl`, from their synthetic-
  query harness) shows a *correct* top-1 match scoring as low as 0.4693 —
  nowhere near a naive "must be > 0.5" bar.
- A BM25-only smoke test (bypassing the full pipeline, see the Stage C
  report) found a genuinely nonsense but real-word query ("quantum flux
  capacitor mounting bracket for interdimensional teleportation") scoring
  in the same range as legitimate low-rank candidates for real queries.

An absolute cutoff on a score with those properties is not a safety net,
it's a coin flip. What stays meaningful *within one response*, even if the
absolute numbers don't compare across responses, is documented below.

Calibration honesty
---------------------
The thresholds below are set from the handful of real numbers available
(two logged interactions, a four-query BM25 smoke test, 18 standards).
That is evidence, not a guess — but it is thin evidence. Revisit these
constants once real usage data exists; `min_margin=0.10` should not be
read as a precise, validated figure.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Literal

from contracts.retrieval import RetrievalCandidate
from knowledge_reasoning.ports.graph_repository import GraphRepository

OrphanReason = Literal[
    "no_candidates",
    "single_candidate_no_corroboration",
    "insufficient_margin",
    "flat_score_distribution",
    "below_absolute_floor",
]


@dataclass(frozen=True)
class OrphanGateConfig:
    # Primary signal: rank-1 vs rank-2 score gap. Calibrated against two
    # real logged accept cases (margins 0.1305 and 0.1982) — set below
    # both so a real confident match isn't flagged, with headroom, not at
    # the midpoint of a two-point sample.
    min_margin: float = 0.10

    # Secondary signal: population stdev across all returned scores. A
    # margin can technically clear min_margin while every other candidate
    # sits in a tight cluster near the top two — this catches that shape.
    # Not independently calibrated against real data (no real example of
    # this specific shape was observed); set conservatively low so it
    # only intervenes on genuinely flat distributions.
    min_score_stdev: float = 0.05

    # Tertiary signal, independent of Teammate 2's calibration entirely:
    # does the top candidate sit in a real cluster (>=1 graph edge)? A
    # genuine product standard normally has allied standards; a candidate
    # with none is weak evidence on its own. Can rescue a borderline
    # margin, or fail a single-candidate response that would otherwise
    # pass on score alone.
    require_graph_corroboration_below_margin: float = 0.20

    # Disabled by default (None) — an absolute floor is exactly the
    # untrustworthy signal this module exists to not rely on. Set only as
    # an explicit, deliberate override (e.g. a known-bad low-score regime
    # confirmed some other way), never as the default gate.
    absolute_floor: float | None = None


@dataclass(frozen=True)
class OrphanGateResult:
    orphan: bool
    reason: OrphanReason | None
    margin: float | None
    score_stdev: float | None
    graph_corroborated: bool | None


def _graph_corroborated(is_number: str, graph_repository: GraphRepository | None) -> bool | None:
    if graph_repository is None:
        return None
    result = graph_repository.expand([is_number], max_hops=1)
    return len(result.paths) > 0


def evaluate_orphan_gate(
    candidates: list[RetrievalCandidate],
    graph_repository: GraphRepository | None = None,
    config: OrphanGateConfig = OrphanGateConfig(),
) -> OrphanGateResult:
    """Candidates must already be sorted best-first (as Teammate 2's
    retrieval returns them). `graph_repository` is optional — pass it to
    enable the tertiary signal; omitting it degrades gracefully to
    margin + distribution shape only, never raises.
    """
    if not candidates:
        return OrphanGateResult(
            orphan=True,
            reason="no_candidates",
            margin=None,
            score_stdev=None,
            graph_corroborated=None,
        )

    scores = [c.score for c in candidates]

    if config.absolute_floor is not None and scores[0] < config.absolute_floor:
        return OrphanGateResult(
            orphan=True,
            reason="below_absolute_floor",
            margin=None,
            score_stdev=statistics.pstdev(scores) if len(scores) > 1 else None,
            graph_corroborated=None,
        )

    if len(candidates) == 1:
        corroborated = _graph_corroborated(candidates[0].is_number, graph_repository)
        return OrphanGateResult(
            orphan=not bool(corroborated),
            reason=None if corroborated else "single_candidate_no_corroboration",
            margin=None,
            score_stdev=None,
            graph_corroborated=corroborated,
        )

    margin = scores[0] - scores[1]
    stdev = statistics.pstdev(scores)

    if margin < config.require_graph_corroboration_below_margin:
        corroborated = _graph_corroborated(candidates[0].is_number, graph_repository)
    else:
        corroborated = None

    if margin < config.min_margin:
        if corroborated:
            pass  # graph evidence rescues a borderline-but-not-hopeless margin
        else:
            return OrphanGateResult(
                orphan=True,
                reason="insufficient_margin",
                margin=margin,
                score_stdev=stdev,
                graph_corroborated=corroborated,
            )
    elif stdev < config.min_score_stdev:
        return OrphanGateResult(
            orphan=True,
            reason="flat_score_distribution",
            margin=margin,
            score_stdev=stdev,
            graph_corroborated=corroborated,
        )

    return OrphanGateResult(
        orphan=False, reason=None, margin=margin, score_stdev=stdev, graph_corroborated=corroborated
    )
