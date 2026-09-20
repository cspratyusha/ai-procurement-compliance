"""The untraceable-certification guard (integration decision 6).

Scope note: Part 5's full LLM-backed generator (the brief's Phase 4 —
prompt templates, the general hallucination guard checking IS numbers
against grounding context, multilingual rendering) was never built in this
engagement; everything up to this point has been the repository/adapter
layer and the first pieces of Phase 3 business logic (the orphan gate).
This module is deliberately narrow: it's the specific guard integration
decision 6 asked for, built so it's real and testable today, and callable
by whatever the eventual LLM-backed generator becomes without redesign.

Why this is the highest-risk hallucination surface in the system
--------------------------------------------------------------------
An LLM asked to write about "ISI certification for structural steel" will
happily supply specific-sounding evidence requirements (licence numbers,
test report formats, notification numbers) from its own training data,
because that text is genuinely plausible — ISI marking conventions are
common knowledge. A fabricated evidence requirement doesn't read as a
hallucination; it reads as competent domain knowledge, and it can go
straight into a tender's evaluation criteria. Every other hallucination
this system guards against (a fabricated IS number, say) is at least
checkable against the grounding context mechanically. A fabricated *but
plausible* evidence requirement for a *real* scheme is not.

`CertificationRequirement.traceable` (contracts/cluster.py) is `True` only
when `notification_reference` is populated — i.e. only when
`required_evidence`/`effective_date`/`source_url` can be traced back to a
specific, citable BIS notification. When it's `False`, generated text may
state the scheme and whether it's mandatory (both taken as given from the
`CertificationRequirement` passed in, not invented by the LLM — no caller
populates that field from real category data yet; see INTEGRATION.md's
"certification mapper" entry), but must not state or imply specific
evidence requirements — it must say they aren't recorded and need
verification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from contracts.cluster import CertificationRequirement

# Deliberately broad and case-insensitive: false positives here (rejecting
# safe text) are cheap to fix by rephrasing; false negatives (missing a
# real fabrication) are the failure mode this guard exists to prevent, so
# it errs toward over-triggering.
_EVIDENCE_LANGUAGE_PATTERNS = [
    r"\blicen[cs]e\s+number\b",
    r"\bcm/l\b",
    r"\btest\s+report\b",
    r"\bcertificate\s+number\b",
    r"\brequired\s+evidence\b",
    r"\bevidence\s+required\b",
    r"\bmust\s+(?:submit|provide|furnish)\b",
    r"\bshall\s+(?:submit|provide|furnish)\b",
]
_EVIDENCE_LANGUAGE_RE = re.compile("|".join(_EVIDENCE_LANGUAGE_PATTERNS), re.IGNORECASE)


@dataclass(frozen=True)
class CertificationGuardResult:
    passed: bool
    matched_terms: list[str]


class UngroundedCertificationClaimError(ValueError):
    """Raised by `assert_no_fabricated_evidence` — generated text stated or
    implied certification evidence requirements that `traceable=False`
    means we don't actually have."""


def check_certification_text(
    text: str, certification: CertificationRequirement
) -> CertificationGuardResult:
    """Non-raising check — use this when you want the result, not an
    exception (e.g. to log and regenerate rather than crash a request)."""
    if certification.traceable:
        return CertificationGuardResult(passed=True, matched_terms=[])
    matches = sorted(set(m.group(0).lower() for m in _EVIDENCE_LANGUAGE_RE.finditer(text)))
    return CertificationGuardResult(passed=not matches, matched_terms=matches)


def assert_no_fabricated_evidence(text: str, certification: CertificationRequirement) -> None:
    """Raising form, for a hard-fail pipeline stage."""
    result = check_certification_text(text, certification)
    if not result.passed:
        raise UngroundedCertificationClaimError(
            f"generated text implies certification evidence not present in "
            f"grounding data (traceable=False): matched {result.matched_terms!r} "
            f"in {text!r}"
        )
