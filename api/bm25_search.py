"""BM25 sparse keyword search over the standards corpus."""

from __future__ import annotations

import json
import re
from pathlib import Path

from rank_bm25 import BM25Okapi


_index: BM25Okapi | None = None
_doc_ids: list[str] = []


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokeniser, lowercased."""
    return re.findall(r"[a-z0-9]+", text.lower())


def build_index(standards: list[dict]) -> None:
    """Build an in-memory BM25 index from a list of standard dicts."""
    global _index, _doc_ids
    corpus = []
    _doc_ids = []
    for s in standards:
        text = " ".join([
            s.get("number", ""),
            s.get("title", ""),
            s.get("scope", ""),
            s.get("description", ""),
            " ".join(s.get("keywords", [])),
        ])
        corpus.append(_tokenize(text))
        _doc_ids.append(s["id"])
    _index = BM25Okapi(corpus)


def load_from_db(get_connection):
    """Load standards from database and build the BM25 index."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, number, title, scope, description, keywords_json FROM standards"
        ).fetchall()
    standards = []
    for r in rows:
        kw = r["keywords_json"]
        if isinstance(kw, str):
            kw = json.loads(kw)
        standards.append({
            "id": r["id"],
            "number": r["number"],
            "title": r["title"],
            "scope": r["scope"],
            "description": r["description"],
            "keywords": kw,
        })
    build_index(standards)
    return len(standards)


def search(query: str, top_k: int = 20) -> list[tuple[str, float]]:
    """Return [(standard_id, bm25_score), ...] sorted by score descending."""
    if _index is None:
        return []
    tokens = _tokenize(query)
    if not tokens:
        return []
    scores = _index.get_scores(tokens)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    results = []
    for idx, score in ranked[:top_k]:
        if score > 0:
            results.append((_doc_ids[idx], float(score)))
    return results
