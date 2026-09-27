"""Everyday product words and tender abbreviations, mapped to the words the standards use.

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

# Tender abbreviations. Case-sensitive: short forms are written in capitals,
# and "MS" or "CI" in lower case is usually part of something else. Each maps
# to wording a held standard's title uses; ones the catalogue has no standard
# for (DWC, ERW, MCCB, UPS, CFL, AAC) are left out on purpose. A few need a
# context word, because the letters mean other things elsewhere ("SRC",
# "DI"). Lower-case forms are accepted where they cannot be anything else.
ABBREVIATIONS: List[Tuple[str, str]] = [
    (r"\bOPC\b", "ordinary portland cement"),
    (r"\bPPC\b", "portland pozzolana cement"),
    (r"\bPSC\b(?=.*\bcement\b)", "portland slag cement"),
    (r"\bSRC\b(?=.*\bcement\b)|\bSRPC\b", "sulphate resisting portland cement"),
    (r"\b(?:TMT|tmt)\b|\bFe\s?(?:415|500|550|600)D?\b", "high strength deformed steel bars"),
    # IS 1239 (Part 1) covers black and galvanized mild steel tubes, the usual GI and MS pipes.
    (r"\bGI\s+(?:pipes?|tubes?)\b", "galvanized steel tubes tubulars and other wrought steel fittings"),
    (r"\bGI\s+sheets?\b", "galvanized steel sheets"),
    (r"\bGI\s+wires?\b", "galvanized steel wire"),
    (r"\bMS\s+(?:pipes?|tubes?)\b", "mild steel tubes tubulars and other wrought steel fittings"),
    (r"\bMS\b", "mild steel"),
    (r"\bSS\b", "stainless steel"),
    (r"\bCI\b", "cast iron"),
    (r"\bDI\s+(?:pipes?|fittings?)\b", "ductile iron pipes"),
    (r"\b(?:HDPE|hdpe)\b", "high density polyethylene"),
    (r"\b(?:LDPE|ldpe)\b", "low density polyethylene"),
    (r"\b(?:CPVC|cpvc)\b", "chlorinated polyvinyl chloride"),
    (r"\b(?:UPVC|uPVC|upvc|PVC-U)\b", "unplasticized PVC"),
    (r"\bSWR\b", "unplasticized PVC pipes for soil and waste"),
    (r"\b(?:GRP|FRP)\b", "glass fibre reinforced plastics"),
    (r"\b(?:XLPE|xlpe)\b", "cross-linked polyethylene"),
    (r"\b(?:ACSR|acsr)\b", "aluminium conductors galvanized steel reinforced"),
    (r"\b(?:AAAC|aaac)\b", "aluminium alloy stranded conductors"),
    (r"\bMCBs?\b", "circuit-breakers for overcurrent protection"),
    (r"\bRCCBs?\b", "residual current operated circuit-breakers"),
    (r"\bD\.?G\.?\s+sets?\b", "diesel generating sets"),
    (r"\bRCC\b", "reinforced concrete"),
    (r"\bPCC\b", "plain and reinforced concrete"),
    (r"\b(?:LPG|lpg)\b", "liquefied petroleum gases"),
    (r"\bPPE\b", "personal protective equipment"),
    (r"\bRO\b", "reverse osmosis"),
    (r"\bMDF\b", "medium density fibre boards"),
    (r"\bGGBS\b", "ground granulated blast furnace slag"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), phrase) for p, phrase in EVERYDAY]
_COMPILED_ABBR = [(re.compile(p), phrase) for p, phrase in ABBREVIATIONS]


def expand(query: str) -> Tuple[str, List[str]]:
    """(query with the standards' phrases added, the phrases added)."""
    added: List[str] = []
    lowered = query.lower()
    for pattern, phrase in _COMPILED:
        if pattern.search(lowered) and phrase.lower() not in lowered and phrase not in added:
            added.append(phrase)
    for pattern, phrase in _COMPILED_ABBR:
        if pattern.search(query) and phrase.lower() not in lowered and phrase not in added:
            # "GI pipe" and "MS pipe" add the specific phrase; the bare "MS"
            # entry would then only repeat part of it.
            if any(phrase in a for a in added):
                continue
            added.append(phrase)
    if not added:
        return query, []
    return f"{query} ({'; '.join(added)})", added
