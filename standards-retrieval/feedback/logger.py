"""Appends and reads interaction logs in append-only JSONL format.

JSONL (JSON Lines) format ensures:
- Safe, non-blocking append operations without rewriting the dataset.
- Resilient recovery if a write is interrupted.
- Incremental, streamable reading for downstream dataset builders.
"""
import json
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
    # If path starts with 'data/', resolve relative to project root
    return _BASE_DIR / p


def append_log(log: InteractionLog, path: Union[str, Path] = "data/interaction_logs.jsonl") -> None:
    """Appends a single InteractionLog record as a JSON line to the specified JSONL file.
    
    Args:
        log: Validated InteractionLog instance.
        path: Path to target JSONL file (defaults to data/interaction_logs.jsonl).
    """
    target_path = _resolve_log_path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    log_dict = log.model_dump()
    json_line = json.dumps(log_dict, ensure_ascii=False)

    with open(target_path, "a", encoding="utf-8") as f:
        f.write(json_line + "\n")

    logger.debug(f"[FeedbackLogger] Appended log for query '{log.query[:30]}' to '{target_path}'.")


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
