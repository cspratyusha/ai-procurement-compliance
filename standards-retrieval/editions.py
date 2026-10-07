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


def _year(number: str) -> int:
    m = re.search(r":(\d{4})", number or "")
    return int(m.group(1)) if m else 0


def _part_key(number: str):
    """'IS 14661 (Part 3/Sec 2):2025' sorts by part, then section, numerically."""
    nums = re.findall(r"\d+", number.split(":")[0])[1:]
    return [int(n) for n in nums]


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

    def parts_of(self, number: str, after_year: int = 0) -> List[Any]:
        """Editions in force of the parts of a standard cited without one.

        BIS sometimes revises a standard into parts: IS 2062:2011 was withdrawn
        naming no replacement, and IS 2062 (Part 1):2025 and (Part 2):2026 are
        what BIS publishes now. `after_year` keeps only parts published after
        the withdrawn edition, so parts older than it are not offered as its
        successor. Empty for a number that already names a part.
        """
        base = extract_base_standard_family(number)
        if "(PART" in base:
            return []
        prefix = base + " (PART "
        found = [s for fam, editions in self.by_family.items() if fam.startswith(prefix)
                 for s in editions if getattr(s, "status", "active") == "active"
                 and _year(s.number) > after_year]
        return sorted(found, key=lambda s: _part_key(s.number))

    def replacement(self, standard: Any) -> Dict[str, Any]:
        """What to cite instead of a superseded edition.

        Returns {number, record, held, withdrawn_without_replacement, note}:
          number   the edition in force, when known (None otherwise)
          record   the corpus record for it, when the corpus holds it
          held     whether the corpus holds it
          withdrawn_without_replacement  BIS withdrew it and named nothing
          note     BIS's reason, for a withdrawal with no replacement
          now_in_parts  for a withdrawal with no replacement: the parts of the
                   standard in force, published after it (never a confirmed
                   replacement; BIS names none)
          via      when the replacement was itself withdrawn naming nothing:
                   that edition (IS 226:1975 -> IS 2062:2011, withdrawn)
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
                if held is None:
                    # No edition of it in force: follow its newest edition, which
                    # may itself have been withdrawn (IS 226 -> IS 2062:2011).
                    held = max(self.by_family.get(extract_base_standard_family(nxt), []),
                               key=lambda s: _year(s.number), default=None)
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
        end = self.by_number.get(_key(named)) if named else None
        if end is not None and getattr(end, "withdrawn", False) and not getattr(end, "superseded_by_number", None):
            # The replacement was itself withdrawn, naming nothing: nothing is in force.
            return {"number": None, "record": None, "held": False, "withdrawn_without_replacement": True,
                    "note": getattr(end, "withdrawal_note", None), "via": end.number,
                    "now_in_parts": [s.number for s in self.parts_of(end.number, _year(end.number))]}
        if named:                                   # chain ended on a superseded edition we hold
            return {"number": named, "record": self.by_number.get(_key(named)), "held": True,
                    "withdrawn_without_replacement": False, "note": None}
        return {"number": None, "record": None, "held": False,
                "withdrawn_without_replacement": bool(getattr(standard, "withdrawn", False)),
                "note": getattr(standard, "withdrawal_note", None),
                "now_in_parts": [s.number for s in self.parts_of(standard.number, _year(standard.number))]}
