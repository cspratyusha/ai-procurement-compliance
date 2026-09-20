"""`RetrievalPort` backed by Teammate 2's real HTTP endpoint.

Genuinely functional, not a stub: it will simply fail to connect until
Part 2 exposes `POST {base_url}/retrieve`, which is the correct, honest
behaviour for "the thing it talks to doesn't exist yet" — no silent empty
result. Uses stdlib `urllib` rather than adding an HTTP client dependency;
swap for `httpx`/`requests` later if this needs retries, connection
pooling, or async.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from contracts.retrieval import RetrievalResult


class RetrievalServiceError(RuntimeError):
    """The retrieval endpoint was reachable but returned an error, or its
    response didn't match the RetrievalResult contract."""


class RetrievalServiceUnavailableError(RuntimeError):
    """The retrieval endpoint could not be reached at all."""


class HttpRetrievalPort:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        payload = json.dumps({"query": query, "top_k": top_k}).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/retrieve",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.load(response)
        except urllib.error.URLError as exc:
            raise RetrievalServiceUnavailableError(
                f"could not reach retrieval service at {self._base_url}: {exc}"
            ) from exc

        try:
            return RetrievalResult.model_validate(body)
        except Exception as exc:  # pydantic ValidationError, primarily
            raise RetrievalServiceError(
                f"retrieval service response did not match RetrievalResult: {exc}"
            ) from exc
