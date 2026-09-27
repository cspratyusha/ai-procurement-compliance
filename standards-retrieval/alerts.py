"""Standards-hygiene findings derived from the corpus and the amendment data.

An "alert" here is not a notification someone sent. It is a fact about the
corpus that would change what a tender should cite, computed on demand:

  supersession  this edition is marked superseded, and (where the corpus
                holds it) here is the active edition that replaces it
  amendment     this standard has published amendments in force, so citing
                the bare edition understates the requirement

Both are derived, never authored. There is no alerts table and nothing is
"sent", the finding exists because the data says so, which means it cannot
drift out of step with what the engine would tell you on the search screen.

What this deliberately is NOT
-----------------------------
A live feed. Nothing here watches BIS for newly published revisions; there is
no crawler and no change-detection job. These are findings about data already
in the corpus, and the "when" of a real alert, the moment a revision was
published, is not knowable from it. So no finding carries a timestamp, and
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
from editions import Editions
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
    """One finding per superseded or withdrawn standard in the corpus."""
    index = Editions(corpus)

    findings: List[Dict[str, Any]] = []
    for standard in corpus:
        if getattr(standard, "status", "active") != "superseded":
            continue

        found = index.replacement(standard)
        replacement = found["record"] if found["held"] else None
        if found["number"] and not found["held"]:
            # BIS names the replacement, but the corpus does not hold its text.
            findings.append({
                "kind": "supersession",
                "severity": SEVERITY_CRITICAL,
                "standard": standard.number,
                "title": standard.title,
                "category": getattr(standard, "category", "") or "",
                "replacement": found["number"],
                "replacement_title": None,
                "detail": (
                    f"BIS lists {standard.number} as withdrawn and replaced by "
                    f"{found['number']}. This corpus does not hold the new edition's text, "
                    f"so check its requirements before citing it."
                ),
                "action": f"Cite {found['number']} instead.",
            })
            continue
        if found["withdrawn_without_replacement"]:
            reason = f" ({found['note']})" if found["note"] else ""
            findings.append({
                "kind": "supersession",
                "severity": SEVERITY_WARNING,
                "standard": standard.number,
                "title": standard.title,
                "category": getattr(standard, "category", "") or "",
                "replacement": None,
                "replacement_title": None,
                "detail": (
                    f"BIS lists {standard.number} as withdrawn with no replacement{reason}."
                ),
                "action": "Do not cite it. Specify the requirement directly or find a current standard that covers it.",
            })
            continue
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
        # A superseded edition already has its own finding: cite the current
        # edition. Its old amendments are not the advice.
        if getattr(standard, "status", "active") == "superseded":
            continue
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
                f"{amendments_data.describe(info, standard.number)} "
                f"Citing the bare edition understates the current requirement."
            ),
            "action": info.get("citation") or standard.number,
        })

    return findings


# The corpus is loaded once per process, so its findings are too. Scanning
# 21,848 standards on every request took ~0.8 s.
_CACHE: Dict[int, List[Dict[str, Any]]] = {}


def findings(category: Optional[str] = None) -> Dict[str, Any]:
    """Every standards-hygiene finding the current corpus supports.

    Ordered by severity so the ones that would actually invalidate a tender
    clause come first. `category` filters to one sector.
    """
    corpus = load_corpus()

    key = id(corpus)  # a reloaded corpus is a new list, so this stays correct
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = _supersession_findings(corpus) + _amendment_findings(corpus)
    items = list(_CACHE[key])

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

    # Checked means the standard's own text was read for amendment slips (or it
    # was researched by hand). A standard with no text is unchecked.
    checked = sum(1 for s in corpus if amendments_data.for_standard(s.number)["status"] != "unchecked")

    return {
        "corpus_size": len(corpus),
        "superseded_in_corpus": sum(
            1 for s in corpus if getattr(s, "status", "active") == "superseded"
        ),
        "amendments_researched": checked,
        "amendments_unchecked": max(len(corpus) - checked, 0),
        "note": (
            "Supersession is read from the corpus, which marks status per record. "
            "Amendments are read from the amendment slips in each standard's archived "
            "copy, plus a few researched by hand. A copy only holds amendments issued "
            "before it was made, so a standard with no amendment finding may still have "
            "later ones: that is not a statement that it has none. Nothing here "
            "monitors BIS for newly published amendments."
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

    statuses: Dict[str, int] = {}
    for standard in corpus:
        status = certification.lookup(standard.number).get("status", "not_verified")
        statuses[status] = statuses.get(status, 0) + 1

    superseded = sum(1 for s in corpus if getattr(s, "status", "active") == "superseded")

    # Counted over the corpus served, not the whole amendments file, so each
    # figure stays a share of the standards the engine actually holds.
    with_amendments = checked = total_amendments = 0
    for standard in corpus:
        info = amendments_data.for_standard(standard.number)
        if info["status"] != "unchecked":
            checked += 1
        if info["checked"] and info.get("count"):
            with_amendments += 1
            total_amendments += info["count"]

    sectors: Dict[str, int] = {}
    for standard in corpus:
        key = getattr(standard, "category", "") or "uncategorised"
        sectors[key] = sectors.get(key, 0) + 1

    return {
        "corpus_size": total,
        "active": total - superseded,
        "superseded": superseded,
        "certification_mandatory": statuses.get("in_force", 0),
        "certification_deferred": statuses.get("deferred", 0),
        "certification_related": statuses.get("related_listed", 0),
        "certification_not_listed": statuses.get("not_listed", 0) + statuses.get("checked_none", 0),
        "certification_not_verified": statuses.get("not_verified", 0),
        "certification_retrieved": certification.coverage().get("retrieved"),
        # Standards with amendments known (researched, or read from their text),
        # and standards whose text was read at all.
        "amendments_researched": with_amendments,
        "amendments_checked": checked,
        "amendments_total": total_amendments,
        "sectors": [
            {"category": name, "standards": count}
            for name, count in sorted(sectors.items(), key=lambda kv: -kv[1])
        ],
    }
