"""Everyday product words, mapped to the words the standards use.

Standards are titled in technical language: a laptop is "information
technology equipment", a geyser a "storage type electric water heater", a
plastic water tank a "rotational moulded polyethylene water storage tank". A
buyer types the everyday word, shares none of the standard's vocabulary, and
the search finds nothing close.

Each entry here adds the standard's own phrase to the query. Rules:

* An entry exists only where the catalogue holds a standard with that
  phrase; mapping a product the catalogue does not cover onto something else
  would turn an honest "no close match" into a wrong answer.
* Whole words only, and never a word with a second common meaning ("AC" is
  also alternating current, "tablet" also a medicine).
* The additions are returned with the results, so the screen says what was
  searched, as it does for a translated query.
"""

import re
from typing import List, Tuple

# (pattern over the lower-cased query, phrase the standards use)
EVERYDAY: List[Tuple[str, str]] = [
    (r"\blaptops?\b|\bnotebook computers?\b|\bdesktop computers?\b|\bpersonal computers?\b|\bcomputers?\b",
     "information technology equipment"),
    (r"\bgeysers?\b|\bwater heaters?\b", "storage type electric water heaters"),
    (r"\belectric kettles?\b|\bkettles?\b", "electric kettles and jugs"),
    (r"\bsolar panels?\b|\bsolar modules?\b|\bsolar plates?\b", "crystalline silicon terrestrial photovoltaic modules"),
    (r"\b(?:plastic|pvc|overhead|loft) (?:water )?tanks?\b|\bwater (?:storage )?tanks?\b",
     "rotational moulded polyethylene water storage tanks"),
    (r"\b(?:mobile|phone|laptop|usb) chargers?\b|\bchargers?\b|\bpower adapters?\b", "switch mode power supply"),
    (r"\btube ?lights?\b", "tubular fluorescent lamps"),
    (r"\bled bulbs?\b|\bled lamps?\b", "self-ballasted LED lamps for general lighting"),
    (r"\bstreet ?lights?\b", "luminaires for road and street lighting"),
    (r"\bfridges?\b", "household refrigerating appliances"),
    (r"\bmixies?\b|\bmixer grinders?\b", "domestic electric food mixers"),
    (r"\binverter batter(?:y|ies)\b|\bups batter(?:y|ies)\b", "stationary lead acid batteries tubular positive plates"),
    (r"\bsafety shoes?\b|\bsafety boots?\b|\bsteel toe\b", "safety footwear"),
    (r"\bgum ?boots?\b", "rubber boots"),
    (r"\bled tvs?\b|\blcd tvs?\b|\btelevisions?\b|\btv sets?\b", "television receivers"),
    (r"\bair coolers?\b|\bdesert coolers?\b", "evaporative air coolers"),
    (r"\bwater purifiers?\b|\bro purifiers?\b", "drinking water treatment"),
    (r"\bsolar water heaters?\b", "solar flat plate collector"),
    (r"\bbike helmets?\b|\bmotorcycle helmets?\b|\bscooter helmets?\b", "protective helmets for two wheeler riders"),
    (r"\bfire extinguishers?\b", "portable fire extinguishers"),
    (r"\bdustbins?\b|\bgarbage bins?\b|\bwaste bins?\b", "mobile containers for solid waste"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), phrase) for p, phrase in EVERYDAY]


def expand(query: str) -> Tuple[str, List[str]]:
    """(query with the standards' phrases added, the phrases added)."""
    added: List[str] = []
    lowered = query.lower()
    for pattern, phrase in _COMPILED:
        if pattern.search(lowered) and phrase.lower() not in lowered and phrase not in added:
            added.append(phrase)
    if not added:
        return query, []
    return f"{query} ({'; '.join(added)})", added
