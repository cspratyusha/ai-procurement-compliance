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
    # "Computer table" and "computer chair" are furniture, handled below. The
    # safety standard is what applies to a computer (IS 13252, now IS/IEC
    # 62368-1); without "safety" the office-equipment measurement methods won.
    (r"\blaptops?\b|\bnotebook computers?\b|\bdesktop computers?\b|\bpersonal computers?\b"
     r"|\bcomputers?\b(?!\s+(?:tables?|desks?|chairs?|furniture|trolleys?|stands?))",
     "information technology equipment safety"),
    (r"\bcctv\b|\b(?:surveillance|security|ip)\s+cameras?\b", "video surveillance systems for use in security applications"),
    # Not for a solar water heater, which is a different product with its own entry below.
    (r"^(?!.*\bsolar\b).*?(?:\bgeysers?\b|\bwater heaters?\b)", "storage type electric water heaters"),
    (r"\belectric kettles?\b|\bkettles?\b", "electric kettles and jugs"),
    (r"\bsolar panels?\b|\bsolar modules?\b|\bsolar plates?\b", "crystalline silicon terrestrial photovoltaic modules"),
    (r"\b(?:plastic|pvc|overhead|loft) (?:water )?tanks?\b|\bwater (?:storage )?tanks?\b",
     "rotational moulded polyethylene water storage tanks"),
    (r"\b(?:mobile|phone|laptop|usb) chargers?\b|\bchargers?\b|\bpower adapters?\b", "switch mode power supply"),
    (r"\btube ?lights?\b", "tubular fluorescent lamps"),
    (r"\bled bulbs?\b|\bled lamps?\b", "self-ballasted LED lamps for general lighting"),
    # The wire in a building's walls is IS 694's PVC insulated cable; "house wiring
    # cable" alone found low-frequency, data and automobile cables. Only when the
    # cable or wire is what is bought: "switches for domestic wiring" are switches.
    (r"^(?=.*\b(?:cables?|wires?)\b)(?:.*\b(?:house|home|domestic|building|internal|indoor|electrical)\s+wiring\b"
     r"|.*\bwiring\s+(?:inside|in)\s+(?:a\s+|the\s+)?(?:house|home|building|office))",
     "polyvinyl chloride insulated cables with rigid and flexible conductor for building wiring"),
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
    (r"\bhume pipes?\b|\bspun pipes?\b", "precast concrete pipes"),
    # The meter on a house is a "watthour meter" in the standards (IS 13779, class 1
    # and 2); "electric meter" alone found the meter-reading data exchange
    # standard, and "watthour meters" alone the transformer-operated class 0.2S ones.
    (r"\b(?:electric|electricity|energy|power|kwh|single phase|three phase) meters?\b",
     "AC static watthour meters class 1 and 2"),
    # IS 3196 (Part 1) names the domestic LPG cylinder by its construction.
    (r"\b(?:domestic|household|home|cooking)\b.*\blpg\b.*\bcylinders?\b|\blpg\b.*\bcylinders?\b.*\b(?:domestic|household|home)\b",
     "welded low carbon steel cylinders for low pressure liquefiable gases"),
    # Fly ash is what BIS calls pulverized fuel ash (IS 12894, fly ash-lime bricks).
    (r"\bfly[\s-]?ash(?:[\s-]lime)? bricks?\b", "pulverized fuel ash-lime bricks"),
    # IS 4984 is titled "Polyethylene pipes for water supply"; HDPE pipes for
    # sewers, gas or cable ducts have standards of their own, so only for water.
    (r"\b(?:hdpe|pe|polyethylene) pipes?\b(?=.*\b(?:water|drinking|potable)\b)", "polyethylene pipes for water supply"),
    # One word in the shop, two in the standards (IS 745, handloom cotton bed sheets).
    (r"\bbedsheets?\b", "bed sheets"),
    # Office furniture, in the words of the Furniture (Quality Control) Order, 2025 standards.
    (r"\b(?:office|revolving|executive|computer|ergonomic|swivel|task) chairs?\b", "work chairs"),
    (r"\b(?:visitor|plastic|stacking|folding|cafeteria|canteen) chairs?\b|\bstools?\b",
     "general purpose chairs and stools"),
    (r"\b(?:office|computer|study|conference|writing) (?:tables?|desks?)\b|\bworkstations?\b",
     "tables and desks"),
    (r"\balmirahs?\b|\b(?:steel|filing) (?:cupboards?|cabinets?)\b|\bfiling cabinets?\b",
     "storage units"),
]

# Tender abbreviations. Case-sensitive: short forms are written in capitals,
# and "MS" or "CI" in lower case is usually part of something else. Each maps
# to wording a held standard's title uses; ones the catalogue has no standard
# for (DWC, ERW, ACB, MCCB, VCB, SPD, CFL) are left out on purpose. A few need
# a context word, because the letters mean other things elsewhere ("SRC",
# "DI", and "M20", which is also a bolt thread). Lower-case forms are accepted
# where they cannot be anything else.
ABBREVIATIONS: List[Tuple[str, str]] = [
    # Concrete grades (IS 456 defines M10 to M80). Before RCC, so the fuller
    # phrase wins over "reinforced concrete".
    (r"\bM\s?-?(?:10|15|20|25|30|35|40|45|50|55|60|65|70|75|80)\b(?=.*\b(?:[Cc]oncrete|RCC|PCC|grade)\b)",
     "plain and reinforced concrete"),
    (r"\bNP\s?-?[1-4]\b", "precast concrete pipes"),
    (r"\bAAC\b", "autoclaved cellular aerated concrete blocks"),
    (r"\bRMC\b", "ready-mixed concrete"),
    (r"\bIS(?:MB|MC|LB|JB|HB|WB|A)\s?\d", "hot rolled steel beam column channel and angle sections"),
    (r"\b(?:AB|ABC)\s+cables?\b", "aerial bunched cables"),
    (r"\bPPR(?:-C)?\b", "polypropylene random copolymer pipes"),
    (r"\bVRLA\b|\bSMF\b(?=.*\bbatter)", "stationary regulated lead acid batteries"),
    # A "UPS battery" is the battery, not the UPS.
    (r"\bUPS\b(?!\s+batter)", "uninterruptible power systems"),
    (r"\bRCBOs?\b", "residual current operated circuit-breakers with integral overcurrent protection"),
    (r"\bRMUs?\b", "high-voltage switchgear and controlgear AC metal-enclosed"),
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
    (r"\bDI\s+(?:fittings?|specials?)\b", "ductile iron fittings for pressure pipes"),
    (r"\bDI\s+pipes?\b", "ductile iron pipes"),
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
    (r"\bRCC\s+(?:hume\s+|spun\s+|NP\s?\d\s+)?pipes?\b", "precast concrete pipes"),
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

# Tenders write short forms with full stops: "G.I. pipe", "D.I. fittings",
# "R.C.C. pipes", "H.D.P.E.". They are read as the plain forms above.
_DOTTED = re.compile(r"\b(?:[A-Za-z]\.){2,}")

# What a schedule of rates says about the price, not the goods: "Rates
# including transportation, loading, unloading", "excluding GST levied by GOI",
# "complete as directed by the Engineer-in-charge". Left in, it outweighs the
# product words; it is dropped from the text searched (never from what the
# official typed or sees).
_BOILERPLATE = [
    re.compile(p, re.IGNORECASE) for p in (
        r"\brates?\b[^.;]{0,40}?\b(?:including|inclusive\s+of|excluding|exclusive\s+of)\b[^.;]*",
        r"\b(?:including|inclusive\s+of|excluding|exclusive\s+of)\b[^.;]*?\b(?:transport\w*|carriage|freight|"
        r"loading|unloading|stacking|handling|lead\s+and\s+lift|GST|taxes|duties|octroi|insurance)\b[^.;]*",
        r"\b(?:levied|payable)\s+by\s+(?:the\s+)?(?:GOI|GOM|Govt\w*|government)\b[^.;]*",
        r"\b(?:complete\s+)?(?:as\s+)?(?:directed|approved|instructed)\s+by\s+(?:the\s+)?"
        r"(?:engineer[\s-]in[\s-]charge|EIC|department)\b[^.;]*",
        r"\bcomplete\s+in\s+all\s+respects?\b",
        r"\betc\.?\s+complete\b",
    )
]


def search_text(query: str) -> str:
    """The query as searched: rate and logistics boilerplate taken out."""
    text = query
    for pattern in _BOILERPLATE:
        text = pattern.sub(" ", text)
    text = " ".join(text.split()).strip(" ,;.")
    # Never reduce a query to nothing: a line that is all boilerplate is searched as typed.
    return text if len(text) >= 12 else query


def expand(query: str) -> Tuple[str, List[str]]:
    """(query with the standards' phrases added, the phrases added)."""
    added: List[str] = []
    base = search_text(query)
    plain = _DOTTED.sub(lambda m: m.group(0).replace(".", "").upper(), base)
    lowered = plain.lower()
    for pattern, phrase in _COMPILED:
        if pattern.search(lowered) and phrase.lower() not in lowered and phrase not in added:
            added.append(phrase)
    for pattern, phrase in _COMPILED_ABBR:
        if pattern.search(plain) and phrase.lower() not in lowered and phrase not in added:
            # "GI pipe" and "MS pipe" add the specific phrase; the bare "MS"
            # entry would then only repeat part of it.
            if any(phrase in a for a in added):
                continue
            added.append(phrase)
    if not added:
        return base, []
    return f"{base} ({'; '.join(added)})", added
