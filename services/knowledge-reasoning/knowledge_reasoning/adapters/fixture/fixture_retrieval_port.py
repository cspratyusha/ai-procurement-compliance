"""Mock `RetrievalPort` — the "mock retrieval service" required by brief
section 6, serving fixed canned results for a fixed set of queries from
fixtures/mock_queries.yaml (including one deliberately low-confidence query
that should trip the Phase 3 orphan gate).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import yaml

from contracts.retrieval import RetrievalCandidate, RetrievalResult

DEFAULT_MOCK_QUERIES_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "mock_queries.yaml"
)


class UnknownMockQueryError(KeyError):
    """Raised when a query has no canned entry in fixtures/mock_queries.yaml.

    Deliberately not swallowed into an empty RetrievalResult: an empty
    candidate list is a meaningful, legitimate outcome (feeds the orphan
    gate) and must not be indistinguishable from "this mock doesn't cover
    that query yet, go add it".
    """


class FixtureRetrievalPort:
    def __init__(self, mock_queries_path: Path = DEFAULT_MOCK_QUERIES_PATH) -> None:
        with mock_queries_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or []
        self._by_query: dict[str, dict] = {entry["query"].strip().lower(): entry for entry in raw}

    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        entry = self._by_query.get(query.strip().lower())
        if entry is None:
            raise UnknownMockQueryError(
                f"no mock retrieval data for query {query!r}; add it to "
                f"fixtures/mock_queries.yaml"
            )
        candidates = [
            RetrievalCandidate(**c) for c in entry["candidates"][:top_k]
        ]
        return RetrievalResult(
            query_id=uuid4(),
            normalised_query=entry["normalised_query"],
            original_query=entry["query"],
            original_language=entry["original_language"],
            product_category=entry.get("product_category"),
            candidates=candidates,
        )
