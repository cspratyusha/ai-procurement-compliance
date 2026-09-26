"""Aggregates the query and interaction logs into dashboard figures.

Every number this module returns is counted from a log file. Nothing is
estimated, projected, or filled in with a plausible-looking default: a
dashboard that invents a figure is worse than one that reports zero, because
zero is checkable and an invention is not.

Two consequences of that rule shape the whole module:

1. **Synthetic records are excluded from live counts.** The feedback log was
   seeded with 124 synthetic interactions to bootstrap the LTR ranker, and
   they are real records of a real pipeline run -- but they are not usage.
   Counting them would put a four-figure number on a dashboard nobody has
   used. They are reported separately, under their own name.

2. **An empty log reports as empty.** `queries_total: 0` with
   `has_live_data: false` is the correct answer for an engine nobody has
   searched yet, and the UI is expected to say so rather than render an
   empty chart that looks like a data-loading bug.
"""
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from feedback.logger import read_logs
from feedback.query_log import read_queries

logger = logging.getLogger("standards-retrieval.stats")

# How many recent searches the dashboard's activity table shows.
RECENT_LIMIT = 8


def _parse_ts(value: Any) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp, tolerating a trailing 'Z' and naive values.

    Returns None rather than raising: one unparseable timestamp in a log file
    must not take out the whole dashboard.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Treat a naive timestamp as UTC so comparisons below cannot raise.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _is_live(record: Dict[str, Any]) -> bool:
    """True for a record produced by actual use rather than by seeding.

    Records written before `source` existed are treated as live, since the
    only writer at that time was a served request.
    """
    return record.get("source", "live") == "live"


def _normalise_category(value: str) -> str:
    """Canonical key for a sector, so two spellings of one sector count as one.

    Lowercases, treats `_` and `&` as spaces, and collapses runs of
    whitespace: `electrical_cables` and `Electrical Cables & Wires` both
    reduce to a form differing only by the trailing word, which
    `_CATEGORY_ALIASES` then folds together.
    """
    key = " ".join(value.replace("_", " ").replace("&", " ").lower().split())
    return _CATEGORY_ALIASES.get(key, key)


# Sector spellings that survive the rules above but still mean one sector.
# Keys here are already normalised. Most pairs need no entry -- `cement &
# building materials` and `cement_building_materials` both reduce to
# "cement building materials" on their own; only a genuine wording
# difference needs listing.
_CATEGORY_ALIASES = {
    "electrical cables wires": "electrical cables",
}


def compute_stats(
    query_log_path: str = "data/query_logs.jsonl",
    interaction_log_path: str = "data/interaction_logs.jsonl",
) -> Dict[str, Any]:
    """Count the dashboard's figures from both log files.

    Returns a dict matching the `StatsResponse` contract in main.py. Safe to
    call against missing or empty logs.
    """
    queries = read_queries(path=query_log_path)
    live_queries = [q for q in queries if _is_live(q)]

    # --- Volume -----------------------------------------------------------
    now = datetime.now(timezone.utc)
    cutoff_30d = now - timedelta(days=30)
    cutoff_7d = now - timedelta(days=7)

    last_30d = 0
    last_7d = 0
    for q in live_queries:
        ts = _parse_ts(q.get("timestamp"))
        if ts is None:
            continue
        if ts >= cutoff_30d:
            last_30d += 1
        if ts >= cutoff_7d:
            last_7d += 1

    # --- Match quality ----------------------------------------------------
    #
    # 'none' is the engine stating the corpus does not cover the query. That
    # is the orphan-query count, and it is the most useful number here: it
    # measures the gap between what officials ask for and what the corpus
    # holds, which is exactly what a standards body would want to see.
    confidence_counts = Counter(q.get("confidence", "unknown") for q in live_queries)
    no_match = confidence_counts.get("none", 0)
    match_rate = (
        round(100.0 * (len(live_queries) - no_match) / len(live_queries), 1)
        if live_queries
        else None
    )

    # --- Sector spread ----------------------------------------------------
    #
    # Counted against a normalised key. Corpora disagree on how they spell a
    # sector -- the canonical corpus stores `electrical_cables`, the pilot one
    # `Electrical Cables & Wires` -- and a log written across a corpus switch
    # holds both spellings for one sector. Summing them raw would report the
    # same sector twice and understate each, so the split is closed here
    # rather than left for the UI to paper over.
    category_counts = Counter(
        _normalise_category(q["category"]) for q in live_queries if q.get("category")
    )
    categories = [
        {"category": name, "queries": count}
        for name, count in category_counts.most_common(6)
    ]

    # --- Latency ----------------------------------------------------------
    #
    # Median, not mean: the first search after a cold start loads two
    # transformer models and takes tens of seconds, and one such outlier
    # would drag a mean far away from what a user actually experiences.
    latencies = sorted(
        q["elapsed_ms"] for q in live_queries
        if isinstance(q.get("elapsed_ms"), (int, float))
    )
    median_ms = None
    if latencies:
        mid = len(latencies) // 2
        median_ms = (
            int(latencies[mid])
            if len(latencies) % 2
            else int((latencies[mid - 1] + latencies[mid]) / 2)
        )

    # --- Recent activity --------------------------------------------------
    recent = [
        {
            "query": q.get("query", ""),
            "standard": q.get("top_result_number"),
            "confidence": q.get("confidence", "unknown"),
            "score": q.get("top_score"),
            "timestamp": q.get("timestamp"),
        }
        for q in live_queries[-RECENT_LIMIT:][::-1]
    ]

    # --- Feedback ---------------------------------------------------------
    interactions = read_logs(path=interaction_log_path, limit=100000)
    live_interactions = [i for i in interactions if _is_live(i)]
    synthetic_count = len(interactions) - len(live_interactions)

    action_counts = Counter(i.get("action") for i in live_interactions)
    accepts = action_counts.get("accept", 0)
    decided = accepts + action_counts.get("reject", 0) + action_counts.get("correct", 0)
    acceptance_rate = round(100.0 * accepts / decided, 1) if decided else None

    return {
        "has_live_data": bool(live_queries),
        "queries_total": len(live_queries),
        "queries_last_30d": last_30d,
        "queries_last_7d": last_7d,
        "no_match_queries": no_match,
        "match_rate": match_rate,
        "median_latency_ms": median_ms,
        "categories": categories,
        "recent_queries": recent,
        "feedback_total": len(live_interactions),
        "feedback_accepted": accepts,
        "feedback_rejected": action_counts.get("reject", 0),
        "feedback_corrected": action_counts.get("correct", 0),
        "acceptance_rate": acceptance_rate,
        "synthetic_interactions": synthetic_count,
    }
