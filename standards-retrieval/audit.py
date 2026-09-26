"""Audit a tender document against the standards corpus.

Finds the IS numbers a document actually cites and checks each one, so the
question answered is "is what this tender already says still correct?" —
which is a different and narrower question than "what should this tender
cite?", the one `/retrieve` answers.

Every finding is a comparison between a citation read out of the document and
a record in the corpus. Nothing is inferred about clauses the document does
not contain, and nothing is scored: there is no compliance percentage here,
because a percentage would imply the audit checked everything a tender needs
rather than the handful of properties the corpus can actually verify.

What is checked
---------------
    superseded    the cited edition is marked superseded, and (when the corpus
                  holds it) the active edition is named
    amendments    the citation omits amendments known to be in force
    unknown       the IS number is not in the corpus at all

What is NOT checked, and why it matters
---------------------------------------
Whether the tender cites the *right* standards for its goods. That needs
someone to read the specification and judge it; this module only verifies the
citations that are already present. A document citing nothing produces no
findings, and that is emphatically not a pass — `citations_found: 0` is
reported so the UI can say so rather than showing a clean result.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import amendments as amendments_data
import certification
from data_loader import load_corpus
from retrieval.postprocess import extract_base_standard_family

logger = logging.getLogger("standards-retrieval.audit")

# An IS citation as it appears in a tender.
#
# Deliberately tolerant of the spellings real documents use -- "IS 694:2010",
# "IS:694-2010", "IS 1554 (Part 1):1988", "IS 456" with no edition -- because
# a citation this misses is a citation that goes unchecked, which is the
# failure that matters. False positives are cheap: they resolve to "not in the
# corpus" and are reported as unverifiable rather than as a defect.
_CITATION = re.compile(
    r"""
    \bIS\s*:?\s*                 # 'IS', optional colon, optional spaces
    (\d{1,5})                    # the number
    (\s*\(\s*Parts?\s*[\dIVX]+\s*\))?   # optional '(Part 2)'
    (?:\s*[:\-]\s*(\d{4}))?      # optional edition year
    """,
    re.IGNORECASE | re.VERBOSE,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_MINOR = "minor"
SEVERITY_INFO = "info"


def find_citations(text: str) -> List[Dict[str, Any]]:
    """Every IS number cited in the document, in order of first appearance.

    Duplicates are collapsed: a standard cited five times is one finding, not
    five, but the occurrence count is kept because a standard cited
    repeatedly is more load-bearing in the document than one mentioned once.
    """
    seen: Dict[str, Dict[str, Any]] = {}

    for match in _CITATION.finditer(text or ""):
        number, part, year = match.group(1), match.group(2), match.group(3)

        # Normalise to the corpus spelling: 'IS 1554 (Part 1):1988'.
        cited = f"IS {number}"
        if part:
            part_number = re.sub(r"[^\dIVXivx]", "", part)
            cited += f" (Part {part_number.upper()})"
        if year:
            cited += f":{year}"

        key = cited.upper()
        if key in seen:
            seen[key]["occurrences"] += 1
            continue

        seen[key] = {
            "cited": cited,
            "number": number,
            "part": part.strip() if part else None,
            "year": year,
            "occurrences": 1,
            # Where in the document it appeared, for the UI to quote.
            "context": _context(text, match.start(), match.end()),
        }

    return list(seen.values())


def _context(text: str, start: int, end: int, window: int = 110) -> str:
    """The sentence fragment around a citation, so a finding can be located.

    Whitespace is collapsed because PDF extraction wraps mid-clause, and a
    quote full of hard line breaks is harder to match against the original
    than one reflowed onto a single line.
    """
    left = max(0, start - window)
    right = min(len(text), end + window)
    fragment = " ".join(text[left:right].split())
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(text) else ""
    return f"{prefix}{fragment}{suffix}"


def _corpus_index(corpus: List[Any]) -> Dict[str, Any]:
    """Corpus keyed by upper-cased IS number, for exact citation lookup."""
    return {s.number.upper(): s for s in corpus}


def _family_index(corpus: List[Any]) -> Dict[str, List[Any]]:
    """Corpus grouped by standard family, for edition-independent lookup."""
    families: Dict[str, List[Any]] = {}
    for standard in corpus:
        families.setdefault(extract_base_standard_family(standard.number), []).append(standard)
    return families


def _active_in_family(family: str, families: Dict[str, List[Any]]) -> Optional[Any]:
    """The active edition of a family, when the corpus holds one."""
    active = [s for s in families.get(family, []) if getattr(s, "status", "active") == "active"]
    if not active:
        return None
    return sorted(active, key=lambda s: s.number)[-1]


def audit_text(text: str) -> Dict[str, Any]:
    """Check every IS citation in a document against the corpus.

    Returns findings plus the counts a UI needs to describe what was and was
    not checked. Safe to call on text with no citations at all.
    """
    corpus = load_corpus()
    by_number = _corpus_index(corpus)
    families = _family_index(corpus)

    citations = find_citations(text)
    findings: List[Dict[str, Any]] = []

    for citation in citations:
        cited = citation["cited"]
        record = by_number.get(cited.upper())

        # A citation with no edition year ('IS 456') cannot be checked for
        # supersession -- there is no edition to compare. Resolve it to the
        # family so the amendment check still applies, and say what happened.
        if record is None and not citation["year"]:
            family = extract_base_standard_family(cited)
            record = _active_in_family(family, families)
            if record is not None:
                findings.append(_undated_finding(citation, record))
                continue

        if record is None:
            findings.append(_unknown_finding(citation))
            continue

        if getattr(record, "status", "active") == "superseded":
            family = extract_base_standard_family(record.number)
            replacement = _active_in_family(family, families)
            findings.append(_superseded_finding(citation, record, replacement))
            continue

        amendment_finding = _amendment_finding(citation, record)
        if amendment_finding:
            findings.append(amendment_finding)

    order = {SEVERITY_CRITICAL: 0, SEVERITY_MINOR: 1, SEVERITY_INFO: 2}
    findings.sort(key=lambda f: (order.get(f["severity"], 3), f["cited"]))

    return {
        "citations_found": len(citations),
        "findings": findings,
        "critical_count": sum(1 for f in findings if f["severity"] == SEVERITY_CRITICAL),
        "clean_citations": len(citations) - len(findings),
        "corpus_size": len(corpus),
        "note": (
            "Only the IS numbers this document already cites were checked. Whether "
            "the tender cites the right standards for its goods is not assessed, so "
            "no findings is not a pass."
        ),
    }


def _superseded_finding(citation: Dict[str, Any], record: Any, replacement: Optional[Any]) -> Dict[str, Any]:
    """The cited edition has been superseded."""
    if replacement is not None:
        return {
            "severity": SEVERITY_CRITICAL,
            "kind": "superseded",
            "cited": citation["cited"],
            "title": record.title,
            "occurrences": citation["occurrences"],
            "context": citation["context"],
            "replacement": replacement.number,
            "detail": (
                f"{citation['cited']} is superseded. {replacement.number} is the active "
                f"edition. A supplier can meet the superseded edition and still fail the "
                f"current requirement."
            ),
            "action": f"Replace the citation with {replacement.number}.",
        }

    return {
        "severity": SEVERITY_MINOR,
        "kind": "superseded",
        "cited": citation["cited"],
        "title": record.title,
        "occurrences": citation["occurrences"],
        "context": citation["context"],
        "replacement": None,
        "detail": (
            f"{citation['cited']} is marked superseded, but this corpus does not hold "
            f"the edition that replaces it, so the replacement cannot be named here."
        ),
        "action": "Confirm the current edition with BIS before issuing.",
    }


def _amendment_finding(citation: Dict[str, Any], record: Any) -> Optional[Dict[str, Any]]:
    """The citation omits amendments known to be in force."""
    info = amendments_data.for_standard(record.number)
    if not info.get("checked") or not info.get("count"):
        return None

    count = info["count"]
    return {
        "severity": SEVERITY_MINOR,
        "kind": "amendment",
        "cited": citation["cited"],
        "title": record.title,
        "occurrences": citation["occurrences"],
        "context": citation["context"],
        "replacement": None,
        "amendment_count": count,
        "detail": (
            f"{count} published amendment{'' if count == 1 else 's'} "
            f"{'is' if count == 1 else 'are'} in force for {record.number}, and this "
            f"citation does not mention them."
        ),
        "action": info.get("citation") or record.number,
    }


def _undated_finding(citation: Dict[str, Any], record: Any) -> Dict[str, Any]:
    """A citation with no edition year, which cannot be pinned to an edition."""
    return {
        "severity": SEVERITY_INFO,
        "kind": "undated",
        "cited": citation["cited"],
        "title": record.title,
        "occurrences": citation["occurrences"],
        "context": citation["context"],
        "replacement": record.number,
        "detail": (
            f"{citation['cited']} is cited without an edition year, so which edition "
            f"a supplier must meet is left open. {record.number} is the active edition "
            f"in this corpus."
        ),
        "action": f"Cite {record.number} explicitly.",
    }


def _unknown_finding(citation: Dict[str, Any]) -> Dict[str, Any]:
    """The cited standard is not in the corpus, so nothing can be verified."""
    return {
        "severity": SEVERITY_INFO,
        "kind": "unknown",
        "cited": citation["cited"],
        "title": "",
        "occurrences": citation["occurrences"],
        "context": citation["context"],
        "replacement": None,
        "detail": (
            f"{citation['cited']} is not in this corpus, so its edition and amendment "
            f"status could not be checked. This is a gap in coverage, not a defect in "
            f"the tender."
        ),
        "action": "Verify this citation against the BIS catalogue directly.",
    }
