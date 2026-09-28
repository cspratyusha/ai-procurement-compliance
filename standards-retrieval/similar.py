"""Related product standards: the standards whose scope is closest to a given one.

A standard's references say what it depends on, not what else covers
similar goods. A buyer drafting a cable tender also needs to know the
neighbouring cable standards, because scopes overlap: which one fits the
product is exactly the choice the tender has to get right.

The dense index already holds a vector for every standard (title, scope and
description, embedded with e5-base-v2), so the neighbours are read from it
directly: no model call, a few milliseconds.

Similarity alone is not enough. Measured on the full corpus, the domestic
pressure cooker's nearest neighbours include the commercial pressure cooker
(0.93) and the cooker gasket (0.92), but also a hand grinder (0.92) and
baking powder (0.90): standards written in the same style score alike. So a
neighbour must also share a meaningful word of the title with the standard
("cooker", "helmet", "cable"), which keeps the siblings and drops the
look-alikes. Each neighbour is one standard, not one edition: other editions
of the standard itself are left out, and a superseded neighbour is shown as
its current edition when the corpus holds one.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from retrieval.postprocess import extract_base_standard_family

SIMILARITY_FLOOR = 0.84
_CANDIDATES = 40

# Words that appear in titles of every kind and so say nothing about the product.
_GENERIC = {
    "the", "and", "for", "with", "from", "other", "than", "use", "used", "purpose", "part", "sec", "section",
    "specification", "code", "practice", "requirement", "method", "test", "testing", "general", "guide",
    "guideline", "recommendation", "recommended", "determination", "glossary", "term", "domestic",
    "household", "industrial", "commercial", "type", "grade", "amendment", "revision", "system",
    "equipment", "apparatus", "product", "material", "application", "design", "construction",
    "performance", "safety", "similar", "unified", "sampling", "analysis", "measurement", "high", "low",
    "medium", "light", "heavy", "new", "all", "various", "including", "upto", "working", "voltage",
    # Shared by unrelated products: helmets and firefighters' clothing are both
    # "protective", a UPS and a protection relay both "power".
    "electric", "electrical", "power", "protective", "protection", "particular", "specific",
}

_POSITIONS: Dict[int, Dict[str, int]] = {}


def _positions(ids: List[str]) -> Dict[str, int]:
    key = id(ids)
    if key not in _POSITIONS:
        _POSITIONS.clear()
        _POSITIONS[key] = {sid: i for i, sid in enumerate(ids)}
    return _POSITIONS[key]


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("es") and word[-3] in "sxz":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def title_words(title: str) -> Set[str]:
    """The words of a title that say what the product is."""
    words = {_singular(w) for w in re.findall(r"[a-z]{3,}", (title or "").lower())}
    return words - _GENERIC


def similar_scope(
    standard: Any,
    by_id: Dict[str, Any],
    editions: Any,
    exclude: Iterable[str] = (),
    limit: int = 6,
    floor: float = SIMILARITY_FLOOR,
) -> List[Tuple[Any, float]]:
    """(standard, similarity) for the closest standards by scope, best first.

    `exclude` are IS numbers already shown (cited, or citing this one); any
    edition of those standards is left out too.
    """
    from indexing.embed_index import load_index

    words = title_words(standard.title)
    if not words:
        return []
    try:
        index, ids = load_index()
    except (FileNotFoundError, ValueError):
        return []
    position = _positions(ids).get(standard.id)
    if position is None:
        return []

    vector = index.reconstruct(position).reshape(1, -1)
    scores, found = index.search(vector, min(_CANDIDATES, index.ntotal))

    seen = {extract_base_standard_family(standard.number)}
    seen.update(extract_base_standard_family(n) for n in exclude)
    out: List[Tuple[Any, float]] = []
    for score, i in zip(scores[0], found[0]):
        if i < 0 or i == position or score < floor:
            continue
        other: Optional[Any] = by_id.get(ids[i])
        if other is None or not (title_words(other.title) & words):
            continue
        family = extract_base_standard_family(other.number)
        if family in seen:
            continue
        seen.add(family)
        if getattr(other, "status", "active") == "superseded":
            other = editions.active_in_family(other.number) or other
        out.append((other, float(score)))
        if len(out) >= limit:
            break
    return out
