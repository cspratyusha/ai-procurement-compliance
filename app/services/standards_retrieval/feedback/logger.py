"""Appends and reads interaction logs in append-only JSONL format and PostgreSQL.

JSONL (JSON Lines) format ensures:
- Fast-path append operations for training set builders and retraining.
- Resilient recovery if a write is interrupted.

PostgreSQL table 'interaction_logs' ensures:
- Persistent audit logs alongside relational data stores.
"""
import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Union

from feedback.schema import InteractionLog

logger = logging.getLogger("standards-retrieval.feedback")

_BASE_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_LOG_PATH = _BASE_DIR / "data" / "interaction_logs.jsonl"


def _resolve_log_path(path: Union[str, Path]) -> Path:
    """Resolves log path, ensuring relative paths point to project data directory."""
    p = Path(path)
    if p.is_absolute():
        return p
    return _BASE_DIR / p


def _write_to_postgres(log: InteractionLog) -> None:
    """Writes interaction log entry to PostgreSQL interaction_logs table if database is accessible."""
    database_url = os.getenv("DATABASE_URL", "postgresql+psycopg://procurement:procurement@localhost:55432/procurement")
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(database_url, connect_args={"connect_timeout": 2})
        with engine.begin() as conn:
            candidates_json = json.dumps([c.model_dump() if hasattr(c, "model_dump") else c for c in log.candidates_shown])
            conn.execute(
                text("""
                    INSERT INTO interaction_logs
                    (query_text, input_mode, candidates, user_action, corrected_to_standard_id, created_at)
                    VALUES (:query_text, :input_mode, :candidates, :user_action, :corrected_to_standard_id, :created_at)
                """),
                {
                    "query_text": log.query,
                    "input_mode": "text",
                    "candidates": candidates_json,
                    "user_action": log.action,
                    "corrected_to_standard_id": log.corrected_id or log.chosen_id,
                    "created_at": log.timestamp
                }
            )
        logger.debug(f"[FeedbackLogger] Successfully synced log to PostgreSQL for query '{log.query[:30]}'")
    except Exception as exc:
        # Graceful non-blocking fallback if PG is offline
        logger.debug(f"[FeedbackLogger] PG sync skipped ({exc})")


def append_log(
    log: InteractionLog,
    path: Union[str, Path] = "data/interaction_logs.jsonl",
    sync_to_db: bool = True
) -> None:
    """Appends a single InteractionLog record to JSONL (fast path) and syncs to PostgreSQL.
    
    Args:
        log: Validated InteractionLog instance.
        path: Path to target JSONL file (defaults to data/interaction_logs.jsonl).
        sync_to_db: If True, attempts write to PostgreSQL interaction_logs table.
    """
    target_path = _resolve_log_path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    log_dict = log.model_dump()
    json_line = json.dumps(log_dict, ensure_ascii=False)

    with open(target_path, "a", encoding="utf-8") as f:
        f.write(json_line + "\n")

    logger.debug(f"[FeedbackLogger] Appended log for query '{log.query[:30]}' to '{target_path}'.")

    if sync_to_db:
        _write_to_postgres(log)


def read_logs(path: Union[str, Path] = "data/interaction_logs.jsonl", limit: int = 50) -> List[Dict[str, Any]]:
    """Reads the last N lines from the interaction logs JSONL file, most recent first.
    
    Args:
        path: Path to the JSONL log file.
        limit: Maximum number of recent log entries to return.
        
    Returns:
        List of log dicts ordered most recent first (descending by timestamp/append order).
    """
    target_path = _resolve_log_path(path)
    if not target_path.exists():
        return []

    lines = []
    with open(target_path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                try:
                    lines.append(json.loads(line_str))
                except json.JSONDecodeError as e:
                    logger.warning(f"[FeedbackLogger] Skipping corrupt JSON line: {e}")

    # Return the last N lines in reverse order (most recent first)
    return lines[-limit:][::-1]
