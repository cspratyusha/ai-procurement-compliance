"""Append-only log of every search the engine actually served.

Separate from `interaction_logs.jsonl`, which records what an official did
with a result set. This file records that a search happened at all, which is
the thing the dashboard needs and the feedback log cannot supply: a query
nobody clicked on is still a query, and a query that matched nothing is the
single most interesting record in the file.

Same JSONL discipline as `feedback/logger.py` -- append-only, one record per
line, a corrupt line skipped rather than failing the read -- so the two can
be read by the same kind of code and neither can lose history to a partial
write.

Nothing here may raise into a request path. A dashboard is a reporting
surface; a search must not fail because its own bookkeeping did.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("standards-retrieval.querylog")

_BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_QUERY_LOG = "data/query_logs.jsonl"


def _resolve(path: Union[str, Path]) -> Path:
    """Resolve a relative path against the project root, as feedback/logger.py does."""
    p = Path(path)
    return p if p.is_absolute() else _BASE_DIR / p


def append_query(
    *,
    query: str,
    top_result_id: Optional[str],
    top_result_number: Optional[str],
    top_score: Optional[float],
    confidence: str,
    category: Optional[str],
    result_count: int,
    corpus_size: int,
    elapsed_ms: Optional[int],
    source: str,
    timestamp: str,
    language: Optional[str] = None,
    path: Union[str, Path] = DEFAULT_QUERY_LOG,
) -> None:
    """Record one served search.

    Stores the top result rather than the whole ranked list: the dashboard
    only ever reports the head of the list, and writing ten candidates per
    search would grow the file ten times faster for data nothing reads.

    Never raises. A failure to log is reported at WARNING and swallowed --
    the caller is in the middle of answering a user.
    """
    record = {
        "query": query,
        "top_result_id": top_result_id,
        "top_result_number": top_result_number,
        "top_score": top_score,
        "confidence": confidence,
        "category": category,
        "result_count": result_count,
        "corpus_size": corpus_size,
        "elapsed_ms": elapsed_ms,
        "language": language,
        "source": source,
        "timestamp": timestamp,
    }

    try:
        target = _resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001 -- logging must never break a search
        logger.warning("[QueryLog] Could not record query: %s", e)


def read_queries(
    path: Union[str, Path] = DEFAULT_QUERY_LOG,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Read logged queries, most recent last.

    Returns [] when the file does not exist -- an engine that has not yet
    served a search is the normal first state, not an error. `limit` keeps
    the last N records; None reads the whole file.
    """
    target = _resolve(path)
    if not target.exists():
        return []

    records: List[Dict[str, Any]] = []
    try:
        with open(target, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning("[QueryLog] Skipping corrupt JSON line: %s", e)
    except OSError as e:
        logger.warning("[QueryLog] Could not read query log: %s", e)
        return []

    return records[-limit:] if limit else records
