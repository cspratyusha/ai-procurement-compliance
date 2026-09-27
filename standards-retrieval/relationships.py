"""Allied standards: what a standard depends on, and what depends on it.

The problem statement asks for the applicable *cluster*, not a single hit. A
tender that cites IS 694 for cable but omits IS 8130 for the conductor and
IS 10810 for testing is incomplete, and that incompleteness is exactly what
this surfaces.

Two sources, one graph:

* `data/relationships/relationships.json`: links read and typed by hand
  (25 across 16 standards). Authoritative where present.
* `data/relationships/extracted_relationships.json`: links read automatically
  from each standard's own REFERENCES clause and explicit citations
  (`data/extract_references.py`), about 88,000 across 17,000 standards. Each
  carries the passage it was read from, so it can be checked.

Where both describe the same pair, the curated link wins. Nothing is
inferred: a link exists only where the source standard's text cites the
target, or a person recorded it.

Some cited standards are outside the corpus. They are still returned,
flagged `outside_corpus`, because hiding them would silently truncate the
cluster and produce exactly the incomplete citation this is meant to prevent.
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_PATH = _REPO_ROOT / "data" / "relationships" / "relationships.json"
_EXTRACTED_PATH = _REPO_ROOT / "data" / "relationships" / "extracted_relationships.json"

# Popular standards (random sampling, reagent water) are cited by over a
# thousand others. Returning all of them makes a response nobody can read, so
# the reverse list is capped and the true total reported beside it.
REFERENCED_BY_LIMIT = 60

_FORWARD: Optional[Dict[str, List[dict]]] = None
_REVERSE: Optional[Dict[str, List[dict]]] = None
_READ_WITHOUT_CITATIONS: Set[str] = set()
_TYPE_LABELS: Dict[str, str] = {}
_COUNTS = {"curated": 0, "extracted": 0}

# Display order: what the standard is built from first, then how it is tested,
# then the wider context. This is the order a procurement official reads in.
_TYPE_ORDER = [
    "normative_reference",
    "material_spec",
    "test_method",
    "terminology",
    "installation",
    "related_product",
]

_GROUP_HEADINGS = {
    "normative_reference": "Normative references",
    "material_spec": "Material specifications",
    "test_method": "Test methods",
    "terminology": "Terminology",
    "installation": "Installation practice",
    "related_product": "Related product standards",
}

_DEFAULT_EXPLANATIONS = {
    "normative_reference": "Standards this one cites; their provisions apply through the reference.",
    "test_method": "Methods of test or sampling this standard relies on.",
    "terminology": "Vocabulary and definitions this standard uses.",
    "installation": "Codes of practice for installing or laying.",
}


def _normalize(number: str) -> str:
    """Canonical IS number for lookup. Mirrors data/consolidate.py."""
    text = " ".join(number.strip().split())
    text = re.sub(r"\(\s*part\s*", "(Part ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\)", ")", text)
    text = re.sub(r"\s*:\s*", ":", text)
    return text.upper()


def _family(number: str) -> str:
    """The standard without its edition year: 'IS 8130:1984' -> 'IS 8130'."""
    return re.sub(r":\d{4}$", "", _normalize(number))


def _edge(number, title, rel_type, note, outside, method, evidence=None, cited_as=None, found_in=None):
    edge = {
        "number": number,
        "title": title or "",
        "type": rel_type,
        "note": note,
        "outside_corpus": bool(outside),
        "method": method,
    }
    if evidence:
        edge["evidence"] = evidence
    if cited_as:
        edge["cited_as"] = cited_as
    if found_in:
        # 'references' (the standard's references clause) or 'body' (a sentence).
        edge["found_in"] = found_in
    return edge


def _load() -> None:
    global _FORWARD, _REVERSE, _TYPE_LABELS, _READ_WITHOUT_CITATIONS
    if _FORWARD is not None:
        return

    _FORWARD = defaultdict(list)
    _REVERSE = defaultdict(list)
    curated_pairs: Set[tuple] = set()

    if _DATA_PATH.exists():
        payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
        _TYPE_LABELS = payload.get("_meta", {}).get("relation_types", {})
        for rel in payload.get("relationships", []):
            source, target = _normalize(rel["source"]), _normalize(rel["target"])
            curated_pairs.add((source, _family(rel["target"])))
            _FORWARD[source].append(_edge(
                rel["target"], rel.get("target_title", ""), rel["type"], rel.get("note"),
                rel.get("outside_corpus"), "curated",
            ))
            # A reverse edge is only meaningful for a standard we actually hold.
            if not rel.get("outside_corpus"):
                _REVERSE[target].append(_edge(rel["source"], "", rel["type"], rel.get("note"), False, "curated"))
            _COUNTS["curated"] += 1

    if _EXTRACTED_PATH.exists():
        payload = json.loads(_EXTRACTED_PATH.read_text(encoding="utf-8"))
        _READ_WITHOUT_CITATIONS = {_normalize(n) for n in payload.get("read_without_citations", [])}
        for rel in payload.get("relationships", []):
            source = _normalize(rel["source"])
            if (source, _family(rel["target"])) in curated_pairs:
                continue  # the hand-read link is authoritative
            _FORWARD[source].append(_edge(
                rel["target"], "", rel["type"], rel.get("note"), rel.get("outside_corpus"),
                "extracted", rel.get("evidence"), rel.get("cited_as"), rel.get("found_in"),
            ))
            if not rel.get("outside_corpus"):
                _REVERSE[_normalize(rel["target"])].append(_edge(
                    rel["source"], "", rel["type"], None, False, "extracted", rel.get("evidence"),
                ))
            _COUNTS["extracted"] += 1


def _grouped(items: List[dict]) -> List[dict]:
    """Group edges by relation type, in reading order."""
    by_type: Dict[str, List[dict]] = defaultdict(list)
    for item in items:
        by_type[item["type"]].append(item)

    groups = []
    for relation_type in _TYPE_ORDER:
        if relation_type not in by_type:
            continue
        groups.append(
            {
                "type": relation_type,
                "heading": _GROUP_HEADINGS.get(relation_type, relation_type),
                "explanation": _TYPE_LABELS.get(relation_type) or _DEFAULT_EXPLANATIONS.get(relation_type, ""),
                # Curated first within a group, then in number order.
                "standards": sorted(by_type[relation_type], key=lambda s: (s["method"] != "curated", s["number"])),
            }
        )
    return groups


def related_to(is_number: str, referenced_by_limit: int = REFERENCED_BY_LIMIT) -> dict:
    """The cluster around one standard.

    Returns:
      depends_on           grouped edges this standard cites
      referenced_by        standards in the corpus that cite this one (capped)
      referenced_by_total  how many cite it in all, before the cap
      total                number of related standards found
      researched           True when there is recorded data for this standard,
                           including a text that was read and cites nothing.
                           False means nobody has looked, not that it has none.
      text_read            True when its own text was read for citations
    """
    _load()
    key = _normalize(is_number)

    forward = _FORWARD.get(key, [])
    reverse = sorted(_REVERSE.get(key, []), key=lambda s: (s["method"] != "curated", s["number"]))
    text_read = key in _READ_WITHOUT_CITATIONS or any(e["method"] == "extracted" for e in forward)

    return {
        "depends_on": _grouped(forward),
        "referenced_by": reverse[:referenced_by_limit],
        "referenced_by_total": len(reverse),
        "total": len(forward) + len(reverse),
        "researched": bool(forward or reverse or text_read),
        "text_read": text_read,
    }


def coverage() -> dict:
    """How much of the corpus has relationship data, for honest reporting."""
    _load()
    return {
        "standards_with_relationships": len(set(_FORWARD) | set(_REVERSE)),
        "total_relationships": sum(len(v) for v in _FORWARD.values()),
        "curated_relationships": _COUNTS["curated"],
        "extracted_relationships": _COUNTS["extracted"],
    }
