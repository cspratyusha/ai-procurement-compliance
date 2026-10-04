"""Published amendments per standard.

An amendment can change the material, the test regime or the acceptance
criteria. A tender that cites the base edition of a standard which has since
been amended can specify something that is no longer conformant, which is why
the problem statement asks for amendments alongside the latest version.

Four sources, in order of authority:

  BIS portal     data/amendments/bis_portal.json, BIS's new standards portal
                 (data/bis_portal.py): each amendment with its year, including
                 those issued after the Know Your Standard snapshot, and the
                 standards published since
  BIS record     data/amendments/bis_kys.json, BIS's own "Know Your
                 Standard" page for each standard: the official number of
                 amendments as of 1 October 2025 (data/bis_kys.py)
  researched     data/amendments/amendments.json, read by hand from BIS
                 product manuals and published amendment documents
  standard text  data/amendments/extracted_amendments.json, the amendment
                 slips bound into each standard's archived copy, read by
                 data/extract_amendments.py

BIS's record gives the count; the slips give the dates and what changed,
where the copy has them. When the two disagree, both are stated.

A copy only holds the amendments issued before it was made, so an answer read
from text is "at least these", with the year the copy is current to, and says
later amendments may exist. A copy with no slips is "none in the archived
copy", which is never reported as "no amendments". A standard with no text at
all is unchecked. Absence of data must not read as absence of the thing.

Statuses: researched | found_in_text | none_in_copy | unchecked
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_PATH = _REPO_ROOT / "data" / "amendments" / "amendments.json"
_EXTRACTED_PATH = _REPO_ROOT / "data" / "amendments" / "extracted_amendments.json"
_BIS_PATH = _REPO_ROOT / "data" / "amendments" / "bis_kys.json"
_PORTAL_PATH = _REPO_ROOT / "data" / "amendments" / "bis_portal.json"

_CACHE: Optional[Dict[str, dict]] = None
_EXTRACTED: Optional[Dict[str, dict]] = None
_BIS: Optional[Dict[str, dict]] = None
_BIS_META: dict = {}
_PORTAL: Optional[Dict[str, dict]] = None
_PORTAL_META: dict = {}

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
    global _CACHE, _EXTRACTED, _BIS, _BIS_META, _PORTAL, _PORTAL_META
    if _CACHE is not None:
        return
    _CACHE, _EXTRACTED, _BIS, _PORTAL = {}, {}, {}, {}
    if _PORTAL_PATH.exists():
        payload = json.loads(_PORTAL_PATH.read_text(encoding="utf-8"))
        _PORTAL_META = payload.get("_meta", {})
        _PORTAL = {_normalize(k): v for k, v in payload.get("standards", {}).items()}
    if _BIS_PATH.exists():
        payload = json.loads(_BIS_PATH.read_text(encoding="utf-8"))
        _BIS_META = payload.get("_meta", {})
        _BIS = {_normalize(k): v for k, v in payload.get("standards", {}).items()}
    if _DATA_PATH.exists():
        payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
        _CACHE = {_normalize(k): v for k, v in payload.get("standards", {}).items()}
    if _EXTRACTED_PATH.exists():
        payload = json.loads(_EXTRACTED_PATH.read_text(encoding="utf-8"))
        _EXTRACTED = {_normalize(k): v for k, v in payload.get("standards", {}).items()}


def reset_cache() -> None:
    global _CACHE, _EXTRACTED, _BIS, _BIS_FAMILY_TITLE, _PORTAL
    _CACHE, _EXTRACTED, _BIS, _BIS_FAMILY_TITLE, _PORTAL = None, None, None, None, None


# Notes BIS appends to a title that are not part of it (mirrors data/apply_bis_status.py).
_BIS_TITLE_NOTE = re.compile(
    r"\s*\(\s*(?:withdrawn|superseded|tentative|revised|modified|bi-?lingual|[^()]*\brevision\b[^()]*)\s*\)",
    re.IGNORECASE,
)
_BIS_FAMILY_TITLE: Optional[Dict[str, str]] = None


def _clean_title(raw: str) -> str:
    title = " ".join(_BIS_TITLE_NOTE.sub("", raw or "").split()).strip(" .,-")
    return title[:1].upper() + title[1:]


def bis_title(is_number: str) -> Optional[str]:
    """BIS's official title for a standard, or None when BIS has no record of it.

    The edition asked for if BIS has it, otherwise the newest edition of the
    same standard: a citation to "IS 302 (Part 1)" should still read as what it is.
    """
    global _BIS_FAMILY_TITLE
    _load()
    entry = _BIS.get(_normalize(is_number))
    if entry and entry.get("title"):
        return _clean_title(entry["title"]) or None
    if _BIS_FAMILY_TITLE is None:
        _BIS_FAMILY_TITLE = {}
        for key in sorted(_BIS, key=lambda k: k[-4:] if k[-4:].isdigit() else "", reverse=True):
            if _BIS[key].get("title"):
                _BIS_FAMILY_TITLE.setdefault(re.sub(r":\d{4}$", "", key), _BIS[key]["title"])
    family_title = _BIS_FAMILY_TITLE.get(re.sub(r":\d{4}$", "", _normalize(is_number)))
    return _clean_title(family_title) if family_title else None


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
      status          researched | found_in_text | none_in_copy | unchecked
      checked         True when amendments are known (researched or found in text)
      count           amendments known (for found_in_text, at least this many)
      amendments      list of {number, date, readable_date, summary, confidence, source}
      citation        how to cite the standard including its amendments
      copy_as_of      for text answers, the year the archived copy is current to
      note            what the answer rests on and what it cannot say
    """
    _load()
    key = _normalize(is_number)
    bis = _with_portal(_BIS.get(key), _PORTAL.get(key))
    if bis is not None and bis.get("amendment_count") is not None:
        return _official(is_number, bis, _CACHE.get(key), _EXTRACTED.get(key))

    entry = _CACHE.get(key)
    if entry is not None:
        return _researched(is_number, entry)

    extracted = _EXTRACTED.get(key)
    if extracted is None:
        return {
            "status": "unchecked",
            "checked": False,
            "count": None,
            "amendments": [],
            "citation": is_number,
            "copy_as_of": None,
            "note": (
                "Amendments have not been checked for this standard. Confirm the "
                "current amendment status with BIS before citing it in a tender."
            ),
        }

    as_of = extracted.get("copy_as_of")
    if not extracted.get("count_in_copy"):
        return {
            "status": "none_in_copy",
            "checked": False,
            "count": None,
            "amendments": [],
            "citation": is_number,
            "copy_as_of": as_of,
            "note": (
                f"No amendment slips in the archived copy of this standard"
                f"{f' (current to {as_of})' if as_of else ''}. Amendments issued after that "
                "would not appear in it, so confirm with BIS before citing it in a tender."
            ),
        }

    amendments = [
        {
            "number": a["number"],
            "date": a.get("date"),
            "readable_date": _readable_date(a.get("date")),
            "summary": a.get("excerpt"),
            # Read from the slip itself, or known to exist only because a
            # later slip or an "incorporating" note implies it.
            "confidence": "read_from_text" if a.get("source") == "slip" else "implied",
            "source": a.get("source"),
        }
        for a in extracted["amendments"]
    ]
    count = extracted["count_in_copy"]
    return {
        "status": "found_in_text",
        "checked": True,
        "count": count,
        "count_confidence": "at_least",
        "amendments": amendments,
        "citation": _text_citation(is_number, amendments),
        "copy_as_of": as_of,
        "note": (
            f"Read from the amendment slips in the archived copy of this standard"
            f"{f', current to {as_of}' if as_of else ''}. Later amendments may exist; the "
            "citation covers them with 'and any later amendments'. Excerpts are from a "
            "scanned copy and may contain OCR errors."
        ),
    }


def _with_portal(kys: Optional[dict], portal: Optional[dict]) -> Optional[dict]:
    """The Know Your Standard record brought up to date with the portal's.

    The portal is BIS's newer record: where it lists more amendments, the
    later ones were issued after the snapshot, so its list is taken; where it
    lists the same number, its years fill those the older record left blank.
    A standard published after the snapshot has only the portal's record.
    """
    if portal is None or portal.get("amendment_count") is None:
        return kys
    merged = dict(kys or {})
    merged.setdefault("withdrawn", portal.get("withdrawn", False))
    if portal.get("withdrawn"):
        merged["withdrawn"] = True
    old = merged.get("amendment_count")
    if old is None or portal["amendment_count"] >= old:
        merged["amendment_count"] = portal["amendment_count"]
        merged["amendments"] = portal.get("amendments", [])
        merged["from_portal"] = True
    return merged


def _official(is_number: str, bis: dict, researched: Optional[dict], extracted: Optional[dict]) -> dict:
    """BIS's current count, with dates and excerpts from the other sources."""
    official = bis["amendment_count"]
    if bis.get("from_portal"):
        retrieved = _PORTAL_META.get("retrieved")
        source = "BIS's standards portal" + (f" (read {retrieved})" if retrieved else "")
    else:
        retrieved = _BIS_META.get("retrieved")
        source = "BIS's record for this standard" + (f" (read {retrieved})" if retrieved else "")

    # Dates: BIS's own table where it gives years, then the researched entry,
    # then the slips read from the archived copy.
    known: Dict[int, dict] = {}
    for item in (extracted or {}).get("amendments", []):
        known[item["number"]] = {"date": item.get("date"), "summary": item.get("excerpt"),
                                 "confidence": "read_from_text" if item.get("source") == "slip" else "implied",
                                 "source": "standard_text"}
    for item in (researched or {}).get("amendments", []):
        known[item["number"]] = {"date": item.get("date"), "summary": item.get("summary"),
                                 "confidence": item.get("confidence", "likely"), "source": "researched"}
    for item in bis.get("amendments", []):
        if item.get("number") and item.get("year") and not (known.get(item["number"]) or {}).get("date"):
            known[item["number"]] = {**known.get(item["number"], {}), "date": str(item["year"]),
                                     "confidence": "confirmed",
                                     "source": "bis_portal" if bis.get("from_portal") else "bis"}

    in_text = (extracted or {}).get("count_in_copy") or 0
    count = max(official, in_text)
    amendments = []
    for n in range(1, count + 1):
        k = known.get(n, {})
        amendments.append({
            "number": n,
            "date": k.get("date"),
            "readable_date": _readable_date(k.get("date")),
            "summary": k.get("summary"),
            "confidence": k.get("confidence", "listed_by_bis"),
            "source": k.get("source", "bis"),
        })

    if official == 0 and in_text == 0:
        note = f"No amendment issued, according to {source}."
    elif in_text > official:
        note = (f"{source} lists {official or 'no'} amendment{'s' if official != 1 else ''}, but the "
                f"archived copy of the standard carries {in_text} amendment slips. Both are shown; "
                "confirm with BIS before citing.")
    else:
        note = f"{official} amendment{'s' if official != 1 else ''} issued, according to {source}."
        if any(a["date"] is None for a in amendments):
            note += " Dates are shown where the standard's copy or BIS's record gives them."

    return {
        "status": "official",
        "checked": True,
        "count": count or 0,
        "count_confidence": "official" if in_text <= official else "disputed",
        "amendments": amendments,
        "citation": citation(is_number, count, amendments),
        "copy_as_of": (extracted or {}).get("copy_as_of"),
        "note": note,
        "withdrawn": bis.get("withdrawn", False),
        "superseded_by": bis.get("superseded_by") if bis.get("superseded_by") not in (None, "None") else None,
        "reaffirmed": bis.get("reaffirmed"),
    }


def _researched(is_number: str, entry: dict) -> dict:
    amendments: List[dict] = []
    for item in entry.get("amendments", []):
        amendments.append({
            "number": item["number"],
            "date": item.get("date"),
            "readable_date": _readable_date(item.get("date")),
            "summary": item.get("summary"),
            "confidence": item.get("confidence", "likely"),
            "source": "researched",
        })
    return {
        "status": "researched",
        "checked": True,
        "count": entry.get("amendment_count"),
        "count_confidence": entry.get("count_confidence"),
        "amendments": amendments,
        "citation": citation(is_number, entry.get("amendment_count"), amendments),
        "copy_as_of": None,
        "note": entry.get("note"),
    }


def _text_citation(is_number: str, amendments: List[dict]) -> str:
    """'IS 694:2010, including Amendment No. 1 (September 2012) and any later amendments'."""
    latest = amendments[-1]
    date = latest.get("readable_date")
    return (f"{is_number}, including Amendment No. {latest['number']}"
            f"{f' ({date})' if date else ''} and any later amendments")


def citation(is_number: str, count: Optional[int], amendments: List[dict]) -> str:
    """How to cite a researched standard in a tender.

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
        suffix = f" being Amendment No. {latest['number']}{f' ({date})' if date else ''}"
        if count == 1:
            return f"{is_number}, incorporating Amendment No. {latest['number']}" + (
                f" ({date})" if date else ""
            )
        return f"{is_number}, incorporating all {count} amendments, the latest{suffix}"

    plural = "amendment" if count == 1 else "amendments"
    return f"{is_number}, incorporating all {count} published {plural}"


def describe(info: dict, number: str) -> str:
    """One sentence for a finding: how many amendments, and what that rests on."""
    count = info.get("count") or 0
    plural = "" if count == 1 else "s"
    if info.get("status") == "official":
        return (f"{count} amendment{plural} to {number} {'has' if count == 1 else 'have'} been issued, "
                "according to BIS's record for the standard.")
    if info.get("status") == "found_in_text":
        as_of = info.get("copy_as_of")
        return (f"At least {count} amendment{plural} to {number} "
                f"{'is' if count == 1 else 'are'} published (read from its archived copy"
                f"{f', current to {as_of}' if as_of else ''}).")
    return f"{count} published amendment{plural} {'is' if count == 1 else 'are'} in force for {number}."


def coverage() -> dict:
    """How much has been checked, for honest reporting."""
    _load()
    official = {k for k, v in _BIS.items() if v.get("amendment_count") is not None}
    official |= {k for k, v in _PORTAL.items() if v.get("amendment_count") is not None}
    keys = set(_CACHE) | set(_EXTRACTED) | official
    infos = {k: for_standard(k) for k in keys}
    return {
        "standards_checked": len(keys),
        "standards_researched": len(_CACHE),
        "standards_official": len(official),
        "standards_with_amendments": sum(1 for i in infos.values() if i["count"]),
        "total_amendments": sum(i["count"] or 0 for i in infos.values()),
        "amendments_dated": sum(1 for i in infos.values() for a in i["amendments"] if a.get("date")),
        "bis_retrieved": _BIS_META.get("retrieved"),
        "bis_portal_retrieved": _PORTAL_META.get("retrieved"),
    }
