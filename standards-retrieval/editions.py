"""Which edition replaces a superseded one, following BIS's record.

Two sources say what replaced an edition:

* the corpus itself, when it holds a newer active edition of the same
  standard (the family rule the ranking pipeline also uses), and
* BIS's record for the edition (data/apply_bis_status.py writes it into the
  corpus as superseded_by_number), which can name an edition the corpus does
  not hold.

Replacements chain: IS 10258:1982 was replaced by the 2002 edition, which
BIS lists as replaced by the 2023 edition. `replacement()` follows the chain
to the end, so a tender is pointed at the edition in force rather than at
another withdrawn one.
"""

import re
from typing import Any, Dict, List, Optional

from retrieval.postprocess import extract_base_standard_family

_MAX_HOPS = 6


def _key(number: str) -> str:
    text = " ".join((number or "").split()).upper()
    text = re.sub(r"\s*:\s*", ":", text)
    return re.sub(r"\(\s*PART\s*", "(PART ", text)


_SHARED: Dict[int, "Editions"] = {}


def for_corpus(corpus: List[Any]) -> "Editions":
    """One index per loaded corpus (a reload is a new list, so a new index)."""
    key = id(corpus)
    if key not in _SHARED:
        _SHARED.clear()
        _SHARED[key] = Editions(corpus)
    return _SHARED[key]


class Editions:
    """Indexes over a corpus, built once per corpus load."""

    def __init__(self, corpus: List[Any]):
        self.by_number: Dict[str, Any] = {_key(s.number): s for s in corpus}
        self.by_family: Dict[str, List[Any]] = {}
        for standard in corpus:
            self.by_family.setdefault(extract_base_standard_family(standard.number), []).append(standard)

    def active_in_family(self, number: str) -> Optional[Any]:
        active = [s for s in self.by_family.get(extract_base_standard_family(number), [])
                  if getattr(s, "status", "active") == "active"]
        return sorted(active, key=lambda s: s.number)[-1] if active else None

    def replacement(self, standard: Any) -> Dict[str, Any]:
        """What to cite instead of a superseded edition.

        Returns {number, record, held, withdrawn_without_replacement, note}:
          number   the edition in force, when known (None otherwise)
          record   the corpus record for it, when the corpus holds it
          held     whether the corpus holds it
          withdrawn_without_replacement  BIS withdrew it and named nothing
          note     BIS's reason, for a withdrawal with no replacement
        """
        current, seen = standard, set()
        named = None
        for _ in range(_MAX_HOPS):
            nxt = getattr(current, "superseded_by_number", None)
            if not nxt or _key(nxt) in seen:
                break
            seen.add(_key(nxt))
            named = nxt
            held = self.by_number.get(_key(nxt))
            if held is None and ":" not in nxt:
                # BIS often names the replacement without a year ("IS 15683" for
                # IS 13849:1993): that is the edition of it in force.
                held = self.active_in_family(nxt)
                if held is not None:
                    named = held.number
            if held is None or getattr(held, "status", "active") == "active":
                current = held
                break
            current = held
        if named:
            record = self.by_number.get(_key(named))
            if record is not None and getattr(record, "status", "active") == "active":
                return {"number": record.number, "record": record, "held": True,
                        "withdrawn_without_replacement": False, "note": None}
            if record is None:
                return {"number": named, "record": None, "held": False,
                        "withdrawn_without_replacement": False, "note": None}

        sibling = self.active_in_family(standard.number)
        if sibling is not None and sibling.number != standard.number:
            return {"number": sibling.number, "record": sibling, "held": True,
                    "withdrawn_without_replacement": False, "note": None}
        if named:                                   # chain ended on a superseded edition we hold
            return {"number": named, "record": self.by_number.get(_key(named)), "held": True,
                    "withdrawn_without_replacement": False, "note": None}
        return {"number": None, "record": None, "held": False,
                "withdrawn_without_replacement": bool(getattr(standard, "withdrawn", False)),
                "note": getattr(standard, "withdrawal_note", None)}
