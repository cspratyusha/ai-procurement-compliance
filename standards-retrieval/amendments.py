"""Published amendments per standard.

An amendment can change the material, the test regime or the acceptance
criteria. A tender that cites the base edition of a standard which has since
been amended can specify something that is no longer conformant, which is why
the problem statement asks for amendments alongside the latest version.

Only researched standards appear here. An absent standard is reported as
unchecked, never as "no amendments" — the same rule as certification and
relationships: absence of data must not read as absence of the thing.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_PATH = _REPO_ROOT / "data" / "amendments" / "amendments.json"

_CACHE: Optional[Dict[str, dict]] = None

_MONTHS = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May", "06": "June", "07": "July", "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December",
}


def _normalize(number: str) -> str:
    text = " ".join(number.strip().split())
    text = re.sub(r"\(\s*part\s*", "(Part ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\)", ")", text)
    text = re.sub(r"\s*:\s*", ":", text)
    return text.upper()


def _load() -> None:
    global _CACHE
    if _CACHE is not None:
        return

    if not _DATA_PATH.exists():
        _CACHE = {}
        return

    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    _CACHE = {_normalize(k): v for k, v in payload.get("standards", {}).items()}


def _readable_date(value: Optional[str]) -> Optional[str]:
    """'2013-05' -> 'May 2013'. Returns None when the date is unknown."""
    if not value:
        return None
    parts = value.split("-")
    if len(parts) == 2 and parts[1] in _MONTHS:
        return f"{_MONTHS[parts[1]]} {parts[0]}"
    return value


def for_standard(is_number: str) -> dict:
    """Amendment status for one standard.

    Returns:
      checked         False when this standard has not been researched
      count           number of amendments in force, when known
      amendments      list of {number, date, readable_date, summary, confidence}
      citation        how to cite the standard including its amendments
    """
    _load()
    entry = _CACHE.get(_normalize(is_number))

    if entry is None:
        return {
            "checked": False,
            "count": None,
            "amendments": [],
            "citation": is_number,
            "note": (
                "Amendments have not been checked for this standard. Confirm the "
                "current amendment status with BIS before citing it in a tender."
            ),
        }

    amendments: List[dict] = []
    for item in entry.get("amendments", []):
        amendments.append(
            {
                "number": item["number"],
                "date": item.get("date"),
                "readable_date": _readable_date(item.get("date")),
                "summary": item.get("summary"),
                "confidence": item.get("confidence", "likely"),
            }
        )

    return {
        "checked": True,
        "count": entry.get("amendment_count"),
        "count_confidence": entry.get("count_confidence"),
        "amendments": amendments,
        "citation": citation(is_number, entry.get("amendment_count"), amendments),
        "note": entry.get("note"),
    }


def citation(is_number: str, count: Optional[int], amendments: List[dict]) -> str:
    """How to cite this standard in a tender.

    The brief asks for a human-readable version + amendment string, e.g.
    "IS 732:2019, incorporating Amendment No. 1 (2021)". Where individual
    amendments are known they are named; where only a count is known the
    count is stated, because "incorporating all 4 amendments" is still
    actionable and does not invent numbers that were never read.
    """
    if not count:
        return is_number

    if amendments:
        latest = amendments[-1]
        date = latest.get("readable_date")
        suffix = f" (Amendment No. {latest['number']}{f', {date}' if date else ''})"
        if count == 1:
            return f"{is_number}, incorporating Amendment No. {latest['number']}" + (
                f" ({date})" if date else ""
            )
        return f"{is_number}, incorporating all {count} amendments, latest{suffix}"

    plural = "amendment" if count == 1 else "amendments"
    return f"{is_number}, incorporating all {count} published {plural}"


def coverage() -> dict:
    """How many standards have been researched, for honest reporting."""
    _load()
    return {
        "standards_checked": len(_CACHE),
        "total_amendments": sum(
            (e.get("amendment_count") or 0) for e in _CACHE.values()
        ),
    }
