"""Plain-language explanations for why each standard matched.

The retrieval stack produces scores. A procurement official needs a sentence.
This asks a local LLM to write one per result, and then refuses to trust it.

The design rule here is that **the LLM may only describe candidates it was
given**. It never chooses which standards to return, never reorders them, and
never contributes to the certification or supersession verdicts. Those come
from retrieval and from curated data, and they stay authoritative. An LLM in a
tool that makes claims about legal requirements is a hallucination risk, so
its output is confined to prose and validated against the candidate list
before it is shown.

Everything is optional. If Ollama is not running the results render exactly as
they did before, without explanations and without an error.
"""

import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request
from typing import Dict, List, Optional

logger = logging.getLogger("standards-retrieval.explanation")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("EXPLANATION_MODEL", "qwen2.5:7b-instruct")

# The first call loads the model into VRAM and can take a minute; later calls
# are a few seconds. Generation is capped so one slow response cannot hold a
# request open indefinitely.
_COLD_TIMEOUT = 120
_WARM_TIMEOUT = 45
_MAX_CANDIDATES = 5

_availability: Optional[bool] = None
_model_loaded = False
_lock = threading.Lock()


def _post(path: str, payload: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        f"{OLLAMA_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def is_available(force_recheck: bool = False) -> bool:
    """Whether a usable Ollama server with the expected model is reachable."""
    global _availability

    if _availability is not None and not force_recheck:
        return _availability

    with _lock:
        try:
            request = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
            with urllib.request.urlopen(request, timeout=3) as response:
                tags = json.loads(response.read().decode("utf-8"))
            names = {m.get("name", "") for m in tags.get("models", [])}
            # Ollama reports "qwen2.5:7b-instruct"; accept a bare-name match too.
            _availability = any(
                name == MODEL or name.split(":")[0] == MODEL.split(":")[0]
                for name in names
            )
            if not _availability:
                logger.info(
                    "[Explanation] Ollama is running but %s is not pulled; "
                    "explanations disabled.", MODEL
                )
        except Exception:
            _availability = False
        return _availability


def _build_prompt(query: str, candidates: List[dict]) -> str:
    lines = []
    for index, candidate in enumerate(candidates, 1):
        scope = (candidate.get("scope") or "")[:260]
        lines.append(f"{index}. {candidate['number']} - {candidate['title']}")
        if scope:
            lines.append(f"   Scope: {scope}")

    listing = "\n".join(lines)

    return f"""You are assisting an Indian government procurement official who is writing a tender.

Their requirement: "{query}"

A retrieval engine returned these candidate Indian Standards:
{listing}

For EACH candidate above, write ONE plain-language sentence saying why it does
or does not fit this requirement. Write for a non-specialist: no jargon, no
score numbers, no hedging.

Rules you must follow:
- Only describe the candidates listed above. Do not mention or invent any other standard.
- Do not state whether certification is required; that is decided elsewhere.
- Do not recommend one over another; just explain the fit.
- Use the IS number exactly as written above.

Respond with ONLY valid JSON in this shape, and nothing else:
{{"explanations":[{{"number":"<IS number>","reason":"<one sentence>"}}]}}"""


def _sanitize(reason: str) -> str:
    """Trim to a single clean sentence of reasonable length."""
    text = " ".join(str(reason).split())
    if len(text) > 300:
        text = text[:300].rsplit(" ", 1)[0] + "…"
    return text


def explain(query: str, results: List[dict], timeout: Optional[int] = None) -> Dict[str, str]:
    """Return {is_number: reason} for the top candidates.

    Returns {} whenever anything goes wrong. Explanations are a bonus on top
    of a result set that is already correct and complete, so a failure here
    must never degrade the search itself.
    """
    global _model_loaded

    if not results or not is_available():
        return {}

    candidates = results[:_MAX_CANDIDATES]
    allowed = {c["number"] for c in candidates}

    payload = {
        "model": MODEL,
        "prompt": _build_prompt(query, candidates),
        "stream": False,
        # Ollama's JSON mode constrains decoding, which is what makes a 7B
        # model reliable enough to parse without a retry loop.
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 500},
    }

    try:
        effective_timeout = timeout or (_WARM_TIMEOUT if _model_loaded else _COLD_TIMEOUT)
        response = _post("/api/generate", payload, effective_timeout)
        _model_loaded = True
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        logger.warning("[Explanation] Generation failed: %s", exc)
        return {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("[Explanation] Unexpected failure: %s", exc, exc_info=True)
        return {}

    raw = response.get("response", "")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Salvage the first JSON object if the model wrapped it in prose.
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            logger.warning("[Explanation] Model returned unparseable output.")
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("[Explanation] Model returned unparseable output.")
            return {}

    items = parsed.get("explanations")
    if not isinstance(items, list):
        return {}

    explanations: Dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        number = str(item.get("number", "")).strip()
        reason = item.get("reason")
        if not number or not reason:
            continue

        # The load-bearing check: anything the model invented is dropped.
        # A fabricated IS number in a procurement tool is the worst possible
        # output, so an unrecognised number is discarded rather than shown.
        if number not in allowed:
            logger.warning(
                "[Explanation] Discarding explanation for %r, which was not a candidate.",
                number,
            )
            continue

        explanations[number] = _sanitize(reason)

    return explanations
