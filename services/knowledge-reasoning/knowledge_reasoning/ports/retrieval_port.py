"""Abstraction over Part 2 (Retrieval & Ranking).

My own business logic never imports `RetrievalCandidate`/`RetrievalResult`
construction from a concrete source — it depends on this Protocol only, so
swapping the fixture-backed mock retrieval service for Teammate 2's real
endpoint (once it exists) is a `factory.py` wiring change, not a rewrite.
"""

from __future__ import annotations

from typing import Protocol

from contracts.retrieval import RetrievalResult


class RetrievalPort(Protocol):
    def retrieve(self, query: str, top_k: int) -> RetrievalResult: ...
