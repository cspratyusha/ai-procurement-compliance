"""Mandatory BIS certification lookup.

A procurement officer needs to know whether a product legally requires BIS
certification before a tender goes out, because getting it wrong has real
consequences. So this module is deliberately conservative:

* It only reports a requirement when one was found in the official BIS list.
* It distinguishes "no scheme applies" (checked) from "not verified"
  (not found in the sections of the list we read). Those must never collapse
  into the same answer, because the second one is not a clearance.
* It never infers a requirement from a standard's sector or wording.

Data lives in `data/certification/certification_rules.json`, which records its
own source and retrieval date.
"""

import json
import re
from pathlib import Path
from typing import Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RULES_PATH = _REPO_ROOT / "data" / "certification" / "certification_rules.json"

_RULES_CACHE: Optional[Dict[str, dict]] = None
_WITHDRAWN_CACHE: Optional[Dict[str, dict]] = None

# Plain-language text shown to a procurement official. The scheme name alone
# ("ISI") does not tell them what to do about it.
_SCHEME_EXPLANATION = {
    "ISI": (
        "This product category requires BIS Product Certification. Only suppliers "
        "holding a valid BIS licence may use the ISI mark, and uncertified product "
        "cannot lawfully be supplied. Require the ISI mark and the supplier's BIS "
        "licence number in the tender."
    ),
    "CRS": (
        "This product category falls under the Compulsory Registration Scheme. The "
        "supplier must hold a valid BIS registration number, which should be quoted "
        "in the tender response."
    ),
    "Hallmark": (
        "This product category requires BIS Hallmarking. Require the hallmark and "
        "the supplier's HUID registration."
    ),
    "none": (
        "No mandatory product certification scheme applies to this standard."
    ),
}


def _normalize(number: str) -> str:
    """Canonical IS number for lookup. Mirrors data/consolidate.py."""
    text = " ".join(number.strip().split())
    text = re.sub(r"\(\s*part\s*", "(Part ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\)", ")", text)
    text = re.sub(r"\s*:\s*", ":", text)
    return text.upper()


def _load() -> None:
    global _RULES_CACHE, _WITHDRAWN_CACHE
    if _RULES_CACHE is not None:
        return

    if not _RULES_PATH.exists():
        _RULES_CACHE = {}
        _WITHDRAWN_CACHE = {}
        return

    payload = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    _RULES_CACHE = {_normalize(r["is_number"]): r for r in payload.get("rules", [])}
    _WITHDRAWN_CACHE = {
        _normalize(w["is_number"]): w for w in payload.get("withdrawn_editions", [])
    }


def lookup(is_number: str) -> dict:
    """Certification status for one standard.

    Returns a dict with:
      scheme       'ISI' | 'CRS' | 'Hallmark' | 'none' | 'not_verified'
      mandatory    True only when a scheme was positively confirmed
      explanation  plain-language text for display
      qco, gazette, product  provenance, when known
    """
    _load()
    rule = _RULES_CACHE.get(_normalize(is_number))

    if rule is None:
        return {
            "scheme": "not_verified",
            "mandatory": False,
            "explanation": (
                "Certification status has not been verified for this standard. That is "
                "not the same as 'no certification needed' — check the BIS compulsory "
                "certification lists before relying on this in a tender."
            ),
            "qco": None,
            "gazette": None,
            "product": None,
        }

    scheme = rule["scheme"]
    explanation = _SCHEME_EXPLANATION[scheme]
    if rule.get("note"):
        explanation = f"{explanation} {rule['note']}"

    return {
        "scheme": scheme,
        "mandatory": scheme in {"ISI", "CRS", "Hallmark"},
        "explanation": explanation,
        "qco": rule.get("qco"),
        "gazette": rule.get("gazette"),
        "product": rule.get("product"),
    }


def withdrawn_note(is_number: str) -> Optional[dict]:
    """Known problem with this edition, if any.

    Some entries in the placeholder corpus name editions that were never
    published — IS 8112 and IS 12269 were both merged into IS 269:2015 and
    withdrawn in 2016. Flagging that is more useful than silently serving a
    standard that does not exist.
    """
    _load()
    return _WITHDRAWN_CACHE.get(_normalize(is_number))
