"""Mandatory BIS certification lookup.

A procurement officer needs to know whether a product legally requires BIS
certification before a tender goes out, because getting it wrong has real
consequences. The answer comes from BIS's own published lists of products
under compulsory certification (data/certification/bis_compulsory.json,
parsed by data/certification/parse_bis_compulsory.py):

  ISI       Scheme I, the ISI mark under a BIS licence
  CRS       Scheme II, the Compulsory Registration Scheme
  Scheme X  Scheme X, certification under the Electrical Equipment QCO

Every answer names the order it rests on and when the list was read. The
statuses a standard can have, and they must never collapse into each other:

  in_force        listed, and the order is in force: certification is mandatory
  deferred        listed in an order whose enforcement is deferred: not yet mandatory
  checked_none    researched by hand, and no scheme applies (codes of practice)
  related_listed  not listed itself, but a sibling part or its successor is;
                  the answer says which, rather than guessing
  not_listed      not on BIS's compulsory lists as read on the retrieval date
  not_verified    the lists are not available, so nothing can be said

Matching is by standard family (number and part, not edition): an order
requires conformity to the standard in force, so it applies to the current
edition whichever year BIS happens to print. When the edition looked up
differs from the one BIS lists, the answer says so.

Hand-researched rules (data/certification/certification_rules.json) add the
"checked, none applies" answers for codes of practice and the withdrawn
editions; where both exist, BIS's list wins.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RULES_PATH = _REPO_ROOT / "data" / "certification" / "certification_rules.json"
_BIS_PATH = _REPO_ROOT / "data" / "certification" / "bis_compulsory.json"

MANDATORY_SCHEMES = {"ISI", "CRS", "Scheme X", "Hallmark"}
_SCHEME_NAME = {"ISI": "ISI", "CRS": "CRS", "X": "Scheme X"}

# Plain-language text shown to a procurement official. The scheme name alone
# ("ISI") does not tell them what to do about it.
_SCHEME_EXPLANATION = {
    "ISI": (
        "This product requires BIS Product Certification. Only suppliers holding a valid "
        "BIS licence may use the ISI mark, and uncertified product cannot lawfully be "
        "supplied. Require the ISI mark and the supplier's BIS licence number in the tender."
    ),
    "CRS": (
        "This product falls under the Compulsory Registration Scheme. The supplier must hold "
        "a valid BIS registration number for the model supplied, which should be quoted in "
        "the tender response."
    ),
    "Scheme X": (
        "This product requires BIS certification under Scheme X (Electrical Equipment Quality "
        "Control Order). Require the supplier's BIS certificate of conformity."
    ),
    "Hallmark": (
        "This product requires BIS Hallmarking. Require the hallmark and the supplier's HUID "
        "registration."
    ),
    "none": "No mandatory product certification scheme applies to this standard.",
}

_CACHE: Optional[dict] = None


# --- numbers -----------------------------------------------------------------

def _normalize(number: str) -> str:
    """Canonical IS number for exact lookup. Mirrors data/consolidate.py."""
    text = " ".join(number.strip().split())
    text = re.sub(r"\(\s*part\s*", "(Part ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\)", ")", text)
    text = re.sub(r"\s*:\s*", ":", text)
    return text.upper()


def family(number: str) -> Tuple[str, str, Tuple[str, ...]]:
    """(prefix, base number, parts) with the edition dropped.

    'IS 302 (Part 2/Sec 25):2009', 'IS 302-2-25' -> ('IS', '302', ('2', '25'))
    'IS/IEC 60947-4-1:2000'                      -> ('IS/IEC', '60947', ('4', '1'))
    """
    text = " ".join(number.upper().split())
    m = re.match(r"IS\s*(?:/\s*(IEC|ISO))?\s*[:\-]?\s*(\d+)(.*)", text)
    if not m:
        return ("", text, ())
    prefix = "IS/" + m.group(1) if m.group(1) else "IS"
    rest = re.sub(r":\s*(?:19|20)\d{2}\b.*$", "", m.group(3))
    parts = re.findall(r"(?:PART|SEC(?:TION)?)\s*\.?\s*-?\s*(\d+[A-Z]?)", rest)
    if not parts:
        parts = re.findall(r"-\s*(\d+[A-Z]?)", rest)
    return (prefix, m.group(2), tuple(parts))


def _year(number: str) -> Optional[str]:
    m = re.search(r":\s*((?:19|20)\d{2})\b", number)
    return m.group(1) if m else None


# --- data --------------------------------------------------------------------

def _load() -> dict:
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    curated: Dict[str, dict] = {}
    withdrawn: Dict[str, dict] = {}
    if _RULES_PATH.exists():
        payload = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
        curated = {_normalize(r["is_number"]): r for r in payload.get("rules", [])}
        withdrawn = {_normalize(w["is_number"]): w for w in payload.get("withdrawn_editions", [])}

    listed: Dict[tuple, List[dict]] = {}
    meta: dict = {}
    if _BIS_PATH.exists():
        payload = json.loads(_BIS_PATH.read_text(encoding="utf-8"))
        meta = payload.get("_meta", {})
        for entry in payload.get("entries", []):
            listed.setdefault(family(entry["is_number"]), []).append(entry)

    # Standards BIS has moved a scheme off, read from the migration notice in
    # the CRS list itself: the family's products are now registered against
    # the successor standard.
    migrated: Dict[tuple, dict] = {}
    for entries in listed.values():
        for e in entries:
            notice = e.get("qco") or ""
            m = re.search(r"Migration to (IS/IEC [\d\s:Part]+?\d{4}) from (.+?)(?:\s+S\.?O|$)", notice)
            if m:
                # "IS/IEC 62368 : Part 1 : 2023" -> "IS/IEC 62368-1:2023"
                successor = re.sub(r"\s*:\s*Part\s*(\d+)\s*:\s*", r"-\1:", " ".join(m.group(1).split()))
                for old in re.findall(r"IS\s*\d+(?:\s*:\s*Part\s*\d+)?", m.group(2)):
                    old_family = family(re.sub(r"\s*:\s*Part\s*(\d+)", r" (Part \1)", old))
                    migrated[old_family] = {"successor": successor, "url": e.get("qco_url"),
                                            "scheme": _SCHEME_NAME[e["scheme"]]}

    _CACHE = {"curated": curated, "withdrawn": withdrawn, "listed": listed,
              "migrated": migrated, "meta": meta}
    return _CACHE


def reset_cache() -> None:
    global _CACHE
    _CACHE = None


def lists_available() -> bool:
    return bool(_load()["listed"])


# --- answers -----------------------------------------------------------------

def _products(entries: List[dict], limit: int = 6) -> List[str]:
    return list(dict.fromkeys(e["product"] for e in entries))[:limit]


def _listed_answer(number: str, entries: List[dict]) -> dict:
    in_force = [e for e in entries if e["status"] == "in_force"]
    chosen = in_force or entries
    first = chosen[0]
    scheme = _SCHEME_NAME[first["scheme"]]
    products = _products(chosen)
    listed_as = first["is_number"]

    if in_force:
        explanation = _SCHEME_EXPLANATION[scheme]
        status, mandatory = "in_force", True
        deferred = [e for e in entries if e["status"] == "deferred"]
        if deferred:
            explanation += (
                f" Some further categories under this standard ({'; '.join(_products(deferred, 3))}) "
                "are named in the order but their enforcement is deferred."
            )
    else:
        deferment = first.get("deferment") or {}
        status, mandatory = "deferred", False
        explanation = (
            f"Named in the {first.get('qco') or 'order'}, but enforcement is deferred"
            f"{' by ' + deferment['order'] if deferment.get('order') else ''} until further orders, "
            "so BIS certification is not yet mandatory for it. Check for a notification "
            "bringing it into force before issuing the tender."
        )

    listed_year, asked_year = _year(listed_as), _year(number)
    if listed_year and asked_year and listed_year != asked_year:
        explanation += (
            f" BIS lists the {listed_year} edition ({listed_as}); the order requires the edition in "
            f"force, and this is the {asked_year} edition."
        )

    return {
        "scheme": scheme,
        "status": status,
        "mandatory": mandatory,
        "explanation": explanation,
        "qco": first.get("qco"),
        "gazette": first.get("gazette"),
        "qco_url": first.get("qco_url"),
        "product": "; ".join(products),
        "products": products,
        "listed_as": listed_as,
        "related": [],
        "source": first.get("source"),
    }


def lookup(is_number: str) -> dict:
    """Certification status for one standard. See the module docstring for statuses."""
    data = _load()
    key = family(is_number)
    curated = data["curated"].get(_normalize(is_number))

    base = {
        "qco": None, "gazette": None, "qco_url": None, "product": None,
        "products": [], "listed_as": None, "related": [], "source": None,
    }

    entries = data["listed"].get(key)
    if entries:
        answer = _listed_answer(is_number, entries)
        if curated and curated.get("note") and answer["mandatory"]:
            answer["explanation"] += " " + curated["note"]
        return answer

    if curated is not None and curated.get("scheme") == "none":
        return {**base, "scheme": "none", "status": "checked_none", "mandatory": False,
                "explanation": _SCHEME_EXPLANATION["none"] + (f" {curated['note']}" if curated.get("note") else ""),
                "product": curated.get("product")}

    if not data["listed"]:
        return {**base, "scheme": "not_verified", "status": "not_verified", "mandatory": False,
                "explanation": (
                    "Certification status has not been verified for this standard. That is not the "
                    "same as 'no certification needed'; check the BIS compulsory certification lists "
                    "before relying on this in a tender."
                )}

    retrieved = data["meta"].get("retrieved", "the retrieval date")

    migrated = data["migrated"].get(key)
    if migrated:
        return {**base, "scheme": "related", "status": "related_listed", "mandatory": False,
                "related": [migrated["successor"]], "qco_url": migrated.get("url"),
                "explanation": (
                    f"BIS has moved {migrated['scheme']} for the products this standard covered onto "
                    f"{migrated['successor']}, which replaced it. Specify and require certification "
                    f"against {migrated['successor']} instead."
                )}

    # Related means a parent part, or the general Part 1 that a particular
    # part is used with (IS 302 Part 1 with the IS 302 Part 2 sections, as the
    # household appliances order lists them). Other sections of the same
    # number are unrelated products and are not offered.
    prefix, number_base, parts = key
    candidates = [(prefix, number_base, parts[:i]) for i in range(len(parts))]
    if parts and parts[0] != "1":
        candidates.append((prefix, number_base, ("1",)))
    in_force_siblings = [k for k in dict.fromkeys(candidates)
                         if k in data["listed"]
                         and any(e["status"] == "in_force" for e in data["listed"][k])]
    if in_force_siblings:
        sib_entries = [e for k in in_force_siblings for e in data["listed"][k] if e["status"] == "in_force"]
        numbers = list(dict.fromkeys(e["is_number"] for e in sib_entries))
        scheme = _SCHEME_NAME[sib_entries[0]["scheme"]]
        products = _products(sib_entries, 5)
        return {**base, "scheme": "related", "status": "related_listed", "mandatory": False,
                "related": numbers[:5], "products": products, "product": "; ".join(products),
                "qco": sib_entries[0].get("qco"), "gazette": sib_entries[0].get("gazette"),
                "qco_url": sib_entries[0].get("qco_url"), "source": sib_entries[0].get("source"),
                "explanation": (
                    f"This standard is not listed itself, but {', '.join(numbers[:3])} "
                    f"{'is' if len(numbers) == 1 else 'are'} under compulsory {scheme} certification "
                    f"for: {'; '.join(products)}. If the item being bought is one of those products, "
                    "certification applies; check the order."
                )}

    return {**base, "scheme": "not_listed", "status": "not_listed", "mandatory": False,
            "source": data["meta"].get("sources", {}).get("ISI"),
            "explanation": (
                f"Not on BIS's lists of products under compulsory certification (ISI, CRS and "
                f"Scheme X, as read on {retrieved}). Certification is voluntary for it unless an "
                "order notified after that date adds it."
            )}


# Product-name words that also mean something else, or say too little alone,
# so they never match a query on their own ("tablets" is also a medicine,
# "notebook" also stationery).
_AMBIGUOUS = {
    "tablet", "tablets", "notebook", "notebooks", "monitor", "monitors", "speaker", "speakers",
    "adaptor", "adaptors", "adapter", "adapters", "products", "product", "equipment", "items",
    "type", "types", "general", "others", "other", "parts", "part", "accessories", "systems",
    "system", "devices", "device", "units", "unit", "sets", "set", "materials", "steel", "grade",
    "plain", "sheets", "strips", "coils", "bars", "wire", "wires", "tubes", "pipes", "sections",
    "specification", "domestic", "household", "similar", "purposes", "use", "portable",
}
_ALIAS_INDEX: Optional[List[tuple]] = None
# Head nouns too general to identify a product without a qualifier.
_GENERIC_HEADS = {"pipe", "tube", "sheet", "strip", "plate", "bar", "rod", "wire", "cable", "section",
                  "fitting", "conductor", "coil", "flat", "angle", "channel", "beam", "board", "panel",
                  "box", "bag", "container", "cylinder", "valve", "block", "tile", "paint", "oil"}


# Where a noun phrase's qualifiers start: "power banks for use in ...",
# "cable for working voltages up to 1100 V".
_QUALIFIER = re.compile(r"\b(?:for|with|of|to|used|upto|up|having|in|on|as|from|by|under|above|below)\b")
_STOP = {"the", "a", "an", "and", "or"}


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("es") and word[-3] in "sxz":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


# "Safety of toys", "Performance of solar water heaters": the product is after "of".
_LEAD = re.compile(r"^(?:safety|performance|requirements?|specification|methods?|quality)\s+(?:requirements?\s+)?of\s+")
# Everyday head nouns for the ones BIS uses.
_HEAD_SYNONYMS = {"bulb": "lamp", "tv": "television", "fridge": "refrigerator", "geyser": "heater",
                  "mixie": "mixer", "almirah": "cupboard", "earbud": "earphone", "headset": "headphone"}


# Sizes, ratings and grades describe the item, they are not the item:
# "GI pipe 25 mm medium class" is a pipe, "OPC 43 grade cement" is cement.
_SPEC_WORDS = {"mm", "cm", "m", "kg", "g", "kv", "v", "a", "w", "kw", "kva", "va", "hp", "litre", "liter", "l",
               "sq", "sqmm", "core", "grade", "class", "type", "size", "dia", "medium", "heavy", "light", "double",
               "single", "pole", "phase", "nos", "no", "pcs", "bag", "bags", "thick", "wide", "long", "inch"}


def _head_and_words(text: str):
    """(head noun, other words) of a noun phrase: the thing named, and what qualifies it."""
    text = " ".join(re.sub(r"\([^)]*\)", " ", text.lower()).split())
    text = _LEAD.sub("", text)
    phrase = _QUALIFIER.split(text, maxsplit=1)[0]
    words = [_singular(w) for w in re.findall(r"[a-z][a-z0-9]+", phrase)
             if w not in _STOP and w not in _SPEC_WORDS and not re.search(r"\d", w)]
    if not words:
        return None, set()
    head = _HEAD_SYNONYMS.get(words[-1], words[-1])
    return head, set(words[:-1])


def _aliases():
    """(head, other words, entry) for every name a listed product goes by."""
    global _ALIAS_INDEX
    if _ALIAS_INDEX is not None:
        return _ALIAS_INDEX
    index = []
    for entries in _load()["listed"].values():
        for entry in entries:
            for alias in re.split(r"[/,;]|\band\b|\bor\b|[-–] ", entry["product"]):
                head, others = _head_and_words(alias)
                if not head or len(head) < 3 or (not others and head in _AMBIGUOUS):
                    continue
                index.append((head, others - _AMBIGUOUS, entry))
    _ALIAS_INDEX = index
    return index


def products_for_query(query: str, limit: int = 5) -> List[dict]:
    """Products on BIS's compulsory lists that a query names, most specific first.

    BIS names products in everyday words ("Laptop/Notebook/Tablets", "Power
    Banks", "CCTV Cameras"), so this answers "is this product under
    compulsory certification, and to which standard" even when the catalogue
    holds no standard text for it.

    A product matches when it names the same thing as the query (the head
    noun: a "PVC insulated copper cable" is a cable, not copper) and, if BIS
    qualifies it, the query shares at least one qualifier.
    """
    q_head, q_words = _head_and_words(query)
    if not q_head or q_head in _AMBIGUOUS:
        return []
    hits = []
    for head, others, entry in _aliases():
        if head != q_head:
            continue
        # A listing that shortens to a bare generic word ("...tubes and pipes"
        # gives "pipes") would match every pipe query; it matches only a query
        # that is itself just that word.
        if not others and q_words and head in _GENERIC_HEADS:
            continue
        shared = others & q_words
        # A bare product word ("cement") names every kind BIS lists; a
        # qualified one must share a qualifier with the listing.
        if others and q_words and not shared:
            continue
        hits.append((len(shared) + 1, entry))
    hits.sort(key=lambda h: (-h[0], h[1]["status"] != "in_force"))
    out, seen = [], set()
    for _, entry in hits:
        key = (entry["is_number"], entry["product"])
        if key in seen or entry["is_number"] in {o["is_number"] for o in out}:
            continue
        seen.add(key)
        out.append({
            "product": entry["product"],
            "is_number": entry["is_number"],
            "scheme": _SCHEME_NAME[entry["scheme"]],
            "status": entry["status"],
            "qco": entry.get("qco"),
            "qco_url": entry.get("qco_url"),
        })
        if len(out) >= limit:
            break
    return out


def withdrawn_note(is_number: str) -> Optional[dict]:
    """Known problem with this edition, if any.

    Some entries name editions that were never published: IS 8112 and IS 12269
    were both merged into IS 269:2015 and withdrawn in 2016.
    """
    return _load()["withdrawn"].get(_normalize(is_number))


def all_rules() -> List[dict]:
    """Every standard on BIS's compulsory lists, plus the hand-checked 'none' answers.

    One row per standard family, with the order it traces to. In-force
    obligations first, then deferred ones, then the checked codes of practice.
    """
    data = _load()
    rules: List[dict] = []
    seen = set()
    for key, entries in data["listed"].items():
        number = entries[0]["is_number"]
        answer = _listed_answer(number, entries)
        rules.append({"is_number": number, "category": entries[0].get("category"),
                      "confidence": "confirmed", **answer})
        seen.add(key)

    for rule in data["curated"].values():
        if rule.get("scheme") != "none" or family(rule["is_number"]) in seen:
            continue
        answer = lookup(rule["is_number"])
        rules.append({"is_number": rule["is_number"], "category": None,
                      "confidence": rule.get("confidence", "confirmed"), **answer})

    order = {"in_force": 0, "deferred": 1, "checked_none": 2}
    rules.sort(key=lambda r: (order.get(r["status"], 3), r["is_number"]))
    return rules


def coverage() -> dict:
    """What the mapping covers, so a screen can state its limits."""
    data = _load()
    rules = all_rules()
    in_force = sum(1 for r in rules if r["status"] == "in_force")
    deferred = sum(1 for r in rules if r["status"] == "deferred")
    none = sum(1 for r in rules if r["status"] == "checked_none")
    meta = data["meta"]
    retrieved = meta.get("retrieved")
    return {
        "standards_researched": len(rules),
        "mandatory": in_force,
        "deferred": deferred,
        "no_scheme": none,
        "retrieved": retrieved,
        "sources": meta.get("sources", {}),
        "source": (
            "BIS lists of products under compulsory certification: Scheme I (ISI mark), "
            "Scheme II (Compulsory Registration Scheme) and Scheme X"
            + (f", read on {retrieved}" if retrieved else "")
            + ", each entry with its Quality Control Order."
        ),
        "note": (
            "A standard not on these lists reports 'not_listed': certification is voluntary for it "
            "unless an order notified after the retrieval date adds it. A standard whose sibling part "
            "is listed reports 'related_listed' and names it. Deferred entries are named in an order "
            "whose enforcement is deferred, so they are not reported as mandatory. If the lists are "
            "unavailable every standard reports 'not_verified', which is not a statement that no "
            "certification is required."
        ),
    }
