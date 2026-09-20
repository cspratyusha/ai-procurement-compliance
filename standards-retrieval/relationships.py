"""Allied standards: what a standard depends on, and what depends on it.

The problem statement asks for the applicable *cluster*, not a single hit. A
tender that cites IS 694 for cable but omits IS 8130 for the conductor and
IS 10810 for testing is incomplete, and that incompleteness is exactly what
this surfaces.

Relationships are read from the referred-standards annexes of the standards
themselves and stored in `data/relationships/relationships.json`. Nothing here
is inferred: a link exists only where the source standard actually cites the
target.

Some cited standards are outside the pilot corpus. They are still returned,
flagged `outside_corpus`, because hiding them would silently truncate the
cluster and produce exactly the incomplete citation this is meant to prevent.
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_PATH = _REPO_ROOT / "data" / "relationships" / "relationships.json"

_FORWARD: Optional[Dict[str, List[dict]]] = None
_REVERSE: Optional[Dict[str, List[dict]]] = None
_TYPE_LABELS: Dict[str, str] = {}

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


def _normalize(number: str) -> str:
    """Canonical IS number for lookup. Mirrors data/consolidate.py."""
    text = " ".join(number.strip().split())
    text = re.sub(r"\(\s*part\s*", "(Part ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\)", ")", text)
    text = re.sub(r"\s*:\s*", ":", text)
    return text.upper()


def _load() -> None:
    global _FORWARD, _REVERSE, _TYPE_LABELS
    if _FORWARD is not None:
        return

    _FORWARD = defaultdict(list)
    _REVERSE = defaultdict(list)

    if not _DATA_PATH.exists():
        return

    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    _TYPE_LABELS = payload.get("_meta", {}).get("relation_types", {})

    for rel in payload.get("relationships", []):
        source = _normalize(rel["source"])
        target = _normalize(rel["target"])

        _FORWARD[source].append(
            {
                "number": rel["target"],
                "title": rel.get("target_title", ""),
                "type": rel["type"],
                "note": rel.get("note"),
                "outside_corpus": bool(rel.get("outside_corpus")),
            }
        )

        # A reverse edge is only meaningful for a standard we actually hold.
        if not rel.get("outside_corpus"):
            _REVERSE[target].append(
                {
                    "number": rel["source"],
                    "title": "",
                    "type": rel["type"],
                    "note": rel.get("note"),
                    "outside_corpus": False,
                }
            )


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
                "explanation": _TYPE_LABELS.get(relation_type, ""),
                "standards": sorted(by_type[relation_type], key=lambda s: s["number"]),
            }
        )
    return groups


def related_to(is_number: str) -> dict:
    """The cluster around one standard.

    Returns:
      depends_on      grouped edges this standard cites
      referenced_by   standards in the corpus that cite this one
      total           number of related standards found
      researched      False when this standard has no recorded relationships,
                      which means nobody has looked — not that it has none
    """
    _load()
    key = _normalize(is_number)

    forward = _FORWARD.get(key, [])
    reverse = _REVERSE.get(key, [])

    return {
        "depends_on": _grouped(forward),
        "referenced_by": sorted(reverse, key=lambda s: s["number"]),
        "total": len(forward) + len(reverse),
        "researched": bool(forward or reverse),
    }


def coverage() -> dict:
    """How much of the corpus has relationship data, for honest reporting."""
    _load()
    return {
        "standards_with_relationships": len(set(_FORWARD) | set(_REVERSE)),
        "total_relationships": sum(len(v) for v in _FORWARD.values()),
    }
