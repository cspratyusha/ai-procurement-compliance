"""Standards-hygiene findings derived from the corpus and the amendment data.

An "alert" here is not a notification someone sent. It is a fact about the
corpus that would change what a tender should cite, computed on demand:

  supersession  this edition is marked superseded, and (where the corpus
                holds it) here is the active edition that replaces it
  amendment     this standard has published amendments in force, so citing
                the bare edition understates the requirement

Both are derived, never authored. There is no alerts table and nothing is
"sent" — the finding exists because the data says so, which means it cannot
drift out of step with what the engine would tell you on the search screen.

What this deliberately is NOT
-----------------------------
A live feed. Nothing here watches BIS for newly published revisions; there is
no crawler and no change-detection job. These are findings about data already
in the corpus, and the "when" of a real alert — the moment a revision was
published — is not knowable from it. So no finding carries a timestamp, and
none of them are described as new. Inventing a "2 hours ago" for a fact that
has been sitting in a JSON file since it was written would be exactly the
kind of plausible-looking fiction this codebase avoids.

Coverage is the load-bearing caveat. Amendments are researched for a handful
of standards; a standard absent from that data has not been checked, which is
not a statement that it has none. `coverage()` reports that so the UI can say
so rather than implying a clean bill of health.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import amendments as amendments_data
import certification
from data_loader import load_corpus
from retrieval.postprocess import extract_base_standard_family

logger = logging.getLogger("standards-retrieval.alerts")

# Severity is about what happens if the finding is ignored in a live tender.
#
#   critical  a superseded edition with a known replacement. Citing it is a
#             concrete defect: the replacement exists and should be named.
#   warning   superseded, but the corpus does not hold the replacement, so we
#             can flag the problem without being able to name the fix; or a
#             standard with amendments in force whose bare edition is cited.
SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"


def _active_replacement(standard, corpus_by_family: Dict[str, List[Any]]) -> Optional[Any]:
    """The active edition in the same standard family, when the corpus holds one.

    Same family rule the ranking pipeline uses, so this screen and search
    cannot disagree about what supersedes what.
    """
    family = extract_base_standard_family(standard.number)
    siblings = corpus_by_family.get(family, [])
    active = [s for s in siblings if getattr(s, "status", "active") == "active"]
    if not active:
        return None
    # Latest edition wins when a family somehow holds more than one active
    # entry; the number sorts by edition year after the colon.
    return sorted(active, key=lambda s: s.number)[-1]


def _supersession_findings(corpus: List[Any]) -> List[Dict[str, Any]]:
    """One finding per superseded standard in the corpus."""
    by_family: Dict[str, List[Any]] = {}
    for standard in corpus:
        by_family.setdefault(extract_base_standard_family(standard.number), []).append(standard)

    findings: List[Dict[str, Any]] = []
    for standard in corpus:
        if getattr(standard, "status", "active") != "superseded":
            continue

        replacement = _active_replacement(standard, by_family)
        if replacement is not None:
            findings.append({
                "kind": "supersession",
                "severity": SEVERITY_CRITICAL,
                "standard": standard.number,
                "title": standard.title,
                "category": getattr(standard, "category", "") or "",
                "replacement": replacement.number,
                "replacement_title": replacement.title,
                "detail": (
                    f"{standard.number} is marked superseded in this corpus. "
                    f"{replacement.number} is the active edition. A tender citing "
                    f"the superseded edition should be updated before it is issued."
                ),
                "action": f"Cite {replacement.number} instead.",
            })
        else:
            findings.append({
                "kind": "supersession",
                "severity": SEVERITY_WARNING,
                "standard": standard.number,
                "title": standard.title,
                "category": getattr(standard, "category", "") or "",
                "replacement": None,
                "replacement_title": None,
                "detail": (
                    f"{standard.number} is marked superseded, but this corpus does "
                    f"not hold the edition that replaces it, so the replacement "
                    f"cannot be named here."
                ),
                "action": "Confirm the current edition with BIS before citing it.",
            })

    return findings


def _amendment_findings(corpus: List[Any]) -> List[Dict[str, Any]]:
    """One finding per corpus standard with published amendments in force.

    Only standards actually present in the corpus are reported: an amendment
    record for something the engine cannot serve is not actionable here.
    """
    findings: List[Dict[str, Any]] = []
    for standard in corpus:
        info = amendments_data.for_standard(standard.number)
        if not info.get("checked") or not info.get("count"):
            continue

        count = info["count"]
        findings.append({
            "kind": "amendment",
            "severity": SEVERITY_WARNING,
            "standard": standard.number,
            "title": standard.title,
            "category": getattr(standard, "category", "") or "",
            "replacement": None,
            "replacement_title": None,
            "amendment_count": count,
            "detail": (
                f"{count} published amendment{'' if count == 1 else 's'} "
                f"{'is' if count == 1 else 'are'} in force for {standard.number}. "
                f"Citing the bare edition understates the current requirement."
            ),
            "action": info.get("citation") or standard.number,
        })

    return findings


def findings(category: Optional[str] = None) -> Dict[str, Any]:
    """Every standards-hygiene finding the current corpus supports.

    Ordered by severity so the ones that would actually invalidate a tender
    clause come first. `category` filters to one sector.
    """
    corpus = load_corpus()

    items = _supersession_findings(corpus) + _amendment_findings(corpus)

    if category:
        wanted = category.strip().lower()
        items = [i for i in items if (i.get("category") or "").lower() == wanted]

    # Critical first, then by standard number so the order is stable between
    # requests rather than following corpus insertion order.
    items.sort(key=lambda i: (i["severity"] != SEVERITY_CRITICAL, i["standard"]))

    return {
        "findings": items,
        "critical_count": sum(1 for i in items if i["severity"] == SEVERITY_CRITICAL),
        "coverage": coverage(corpus),
    }


def coverage(corpus: Optional[List[Any]] = None) -> Dict[str, Any]:
    """What these findings are and are not based on.

    Returned with every response so the UI can state the limits of the scan
    rather than presenting an empty or short list as an all-clear.
    """
    if corpus is None:
        corpus = load_corpus()

    amendment_coverage = amendments_data.coverage()
    checked = amendment_coverage.get("standards_checked", 0)

    return {
        "corpus_size": len(corpus),
        "superseded_in_corpus": sum(
            1 for s in corpus if getattr(s, "status", "active") == "superseded"
        ),
        "amendments_researched": checked,
        "amendments_unchecked": max(len(corpus) - checked, 0),
        "note": (
            "Supersession is read from the corpus, which marks status per record. "
            "Amendments have been researched for a small number of standards; a "
            "standard that raises no amendment finding has most likely not been "
            "checked, which is not a statement that it has none. Nothing here "
            "monitors BIS for newly published revisions."
        ),
    }


def corpus_health() -> Dict[str, Any]:
    """Counts describing how complete the corpus's own metadata is.

    Feeds the compliance screen. Every figure is a count over records that
    exist, and each 'researched' count is paired with the total it is out of,
    because 17 certification records reads very differently against 45
    standards than against 4,282.
    """
    corpus = load_corpus()
    total = len(corpus)

    certified = 0
    not_verified = 0
    for standard in corpus:
        rule = certification.lookup(standard.number)
        if rule.get("scheme") == "not_verified":
            not_verified += 1
        elif rule.get("mandatory"):
            certified += 1

    superseded = sum(1 for s in corpus if getattr(s, "status", "active") == "superseded")
    amendment_coverage = amendments_data.coverage()

    sectors: Dict[str, int] = {}
    for standard in corpus:
        key = getattr(standard, "category", "") or "uncategorised"
        sectors[key] = sectors.get(key, 0) + 1

    return {
        "corpus_size": total,
        "active": total - superseded,
        "superseded": superseded,
        "certification_mandatory": certified,
        "certification_not_verified": not_verified,
        "amendments_researched": amendment_coverage.get("standards_checked", 0),
        "amendments_total": amendment_coverage.get("total_amendments", 0),
        "sectors": [
            {"category": name, "standards": count}
            for name, count in sorted(sectors.items(), key=lambda kv: -kv[1])
        ],
    }
