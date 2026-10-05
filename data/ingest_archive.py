"""Ingest Indian Standards from the Public.Resource.Org archive.

The pilot corpus was placeholder data: realistic IS numbers with scope text we
wrote ourselves. This replaces that with the **published scope clause of the
actual standard**, which is the difference between a demo and a usable tool.

Source: the `gov.in.is.*` collection on archive.org, 22,022 Indian Standards
published by Public.Resource.Org on the principle that law citizens must obey
should be freely readable. Each item carries a plain-text rendering alongside
the PDF, so no PDF parsing is needed.

Two things to know about the text:

* It is OCR of scanned documents, so it contains recognition errors
  ("ann" for "and", "tnay" for "may"). We clean the worst of it and record
  that the text is OCR-derived rather than pretending otherwise.
* Clause numbering is consistent enough to locate the SCOPE clause reliably,
  which is the part that matters for retrieval.

Run with::

    python data/ingest_archive.py --list        # what would be fetched
    python data/ingest_archive.py --limit 50    # fetch 50, for a trial run
    python data/ingest_archive.py               # fetch the full target set
    python data/ingest_archive.py --rescope     # re-extract scopes from the cached texts
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = _REPO_ROOT / "data" / "archive" / "ingested_standards.json"
CACHE_DIR = _REPO_ROOT / "data" / "archive" / "cache"
# Archive items whose text is another document (an amendment slip for the next
# number, SP 62's handbook filed as IS 62): their scope is not read.
MISFILED = _REPO_ROOT / "data" / "archive" / "misfiled.json"


def misfiled() -> set:
    return set(json.loads(MISFILED.read_text(encoding="utf-8"))["misfiled"]) if MISFILED.exists() else set()

SEARCH_URL = "https://archive.org/advancedsearch.php"
SCRAPE_URL = "https://archive.org/services/search/v1/scrape"
METADATA_URL = "https://archive.org/metadata/{identifier}"
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"

USER_AGENT = "ai-compliance-sih/1.0 (standards retrieval research; contact via repo)"

# archive.org is a donation-funded public service, so stay modest: a handful
# of concurrent connections rather than a flood. Measured at 5 concurrent
# metadata requests in 2.7 s, which the service handles comfortably.
WORKERS = 8
REQUEST_DELAY = 0.05

# Word boundaries matter here. Without them "tile" matches "textile",
# "meter" matches "diameter", and "angle" matches "triangle" -- so a ceramic
# tile standard lands in textiles and much of the collection lands in
# whichever rule happens to come first.
#
# `measurement_testing` is deliberately LAST. Thousands of standards are
# titled "Methods of test for X", and the subject X is what a procurement
# officer searches for, not the fact that it is a test method. Only standards
# with no other identifiable subject fall through to it.
SECTOR_RULES = [
    ("ppe", r"\bsafety helmet|personal protective|safety footwear|\brespirator|\bgoggle|ear ?muff|safety belt|\bhelmet\b|face shield|safety harness|protective clothing|protective footwear"),
    ("electrical_cables", r"\bcables?\b|\bconductors?\b|\bwires?\b|flexible cord|\bbusbar"),
    ("electrical_installations", r"electrical installation|\bwiring\b|switchgear|\bswitch(es)?\b|\bsocket|\bearthing\b|luminaire|\blighting\b|\btransformer|circuit breaker|\bmotors?\b|\bgenerator\b|\bfuse\b|energy meter"),
    ("plastic_pipes", r"polyethylene pipe|\bPVC\b|unplasticized|\bHDPE\b|\bUPVC\b|plastic pipe|water bar|polypropylene"),
    ("steel_pipes_fittings", r"steel tubes?\b|steel pipes?\b|\btubular\b|pipe fitting|ductile iron pipe|\bflange|cast iron pipe|\bvalves?\b"),
    ("structural_steel", r"structural steel|rolled steel|reinforcement|deformed bar|\bjoist|prestress|\bwelding\b|\bbolts?\b|\bnuts?\b|\brivet|\bfastener|\bsteel\b"),
    ("cement_building_materials", r"\bcement\b|\bconcrete\b|\baggregates?\b|\bbricks?\b|\bmortar\b|masonry|\bplaster\b|pozzolana|fly ash|admixture|\btiles?\b|\bglass\b|\bpaint|\bgypsum\b|\bmarble\b"),
    ("timber_furniture", r"\btimber\b|\bwood\b|\bwooden\b|plywood|\bfurniture\b|particle board|\bveneer\b|block board"),
    ("textiles", r"\btextile|\bfabrics?\b|\byarn\b|\bcotton\b|\bjute\b|\bsilk\b|\bwool\b|\bcanvas\b|\bgarment|\bcloth\b"),
    ("rubber_leather", r"\brubber\b|\bleather\b|\btyres?\b|\btires?\b|elastomer|\bhose\b|\bbelting\b"),
    ("food_agriculture", r"\bfood\b|foodstuff|\bedible\b|agricultur|\bgrain\b|\bcereal|\bspice|\bmilk\b|\bsugar\b|\btea\b|\bcoffee\b|\bfruits?\b|\bvegetable"),
    ("chemicals", r"\bchemical|\bacid\b|\balkali\b|\breagent\b|\bsolvent\b|fertili[sz]er|\bdyes?\b|\bsodium\b|\bsulphate\b|\bchloride\b"),
    ("packaging", r"\bpackaging\b|\bcarton\b|\bcontainers?\b|\bdrums?\b|\bsacks?\b|\bbottles?\b|corrugated"),
    ("water_quality", r"drinking water|water quality|wastewater|\bsewage\b|\beffluent\b|water supply|\bpotable\b|\bsanitary\b|\bplumbing\b"),
    ("geotechnical", r"\bsoils?\b|geotechnical|\bfoundation|bearing capacity|\bpiles?\b|earthwork|\bsubgrade\b|embankment"),
    ("machinery_equipment", r"\bmachine|\bpumps?\b|\bcompressor|\bbearings?\b|\bgears?\b|hydraulic|pneumatic|\bcrane\b|conveyor|\bengine\b|\btools?\b|\blathe\b"),
    ("measurement_testing", r"method(s)? of test|\bsampling\b|calibrat|\bmeasuring\b|\bgauges?\b|\binstrument|test method|\bcaliper"),

    # Families added after sampling what the first pass left unclassified.
    # Each pattern was written against scope clauses that actually appear in
    # the archive rather than guessed from a taxonomy: electronics and
    # metallurgy alone accounted for a large share of the discards, and
    # dropping them meant the corpus silently excluded whole BIS divisions.
    #
    # These sit after the rules above deliberately. Classification is
    # first-match, so the established sectors keep their claim on a record
    # and these only catch what would otherwise have been discarded.
    ("electronics_telecom", r"\belectronic|semiconductor|\btransistor|\bdiode\b|\bcapacitor|\bresistor|\bvaristor\b|printed circuit|telecommunication|\bantenna|\bradio\b|\btelevision\b|signal generator|\bamplifier|integrated circuit|\brelay\b|\bconnector"),
    ("metals_alloys", r"\baluminium\b|\bcopper\b|\bbrass\b|\bbronze\b|\bzinc\b|\bnickel\b|\blead\b|\btin\b|\balloy\b|\bingot|\bcasting|\bforging|\bmetallurg|non-ferrous|\bsmelting|\bfoundry\b"),
    ("paints_coatings", r"\bpaints?\b|\bvarnish|\bpigment|\blacquer|\benamel\b|\bprimer\b|\bcoating|anti-?corrosi|galvani[sz]|electroplat|\bpowder coat"),
    ("petroleum_lubricants", r"\bpetroleum\b|\blubricat|\bgrease\b|\bdiesel\b|\bpetrol\b|\bkerosene\b|\bbitumen|\basphalt|\bcrude oil|fuel oil|\brefiner"),
    ("refractories_ceramics", r"\brefractor|\bceramic|\bdolomite\b|\bfireclay|\bkiln\b|\bporcelain|\bvitreous|\bsilica brick|\bcrucible"),
    ("mechanical_fittings", r"\bfitting|\bcoupling|\bstud\b|\bnipple\b|\belbow\b|\bunion\b|\bspindle|\bbush(ing)?\b|\bwasher\b|\bspring\b|\bseal(s|ing)?\b|\bgasket"),
    ("paper_printing", r"\bpaper\b|\bpaperboard|\bprinting\b|\bink\b|\bstationery|\bcardboard|\bpulp\b"),
    ("automotive", r"\bautomotive|\bvehicle|\bautomobile|\btractor\b|\bmotorcycle|\bbrake\b|\bclutch\b|\bchassis|\bwindscreen"),
    ("medical_laboratory", r"\bmedical\b|\bsurgical|\bhospital|\bsyringe|\bpharmaceutic|\blaborator|\bdental\b|\bdiagnostic"),
]


def http_get(url: str, timeout: int = 45) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def scrape_all(batch: int = 1000):
    """Yield every item in the collection, via the cursor-based scrape API.

    `advancedsearch` cannot page past 10,000 results, it is Solr underneath,
    and deep paging returns a different response shape that has no `response`
    key at all. The first attempt at a full scan died at page 21 for exactly
    that reason, having seen 9,336 of 22,022 standards.

    The scrape service exists for full-collection export and pages by cursor,
    so it has no such ceiling.
    """
    cursor = None
    while True:
        params = {
            "q": "identifier:gov.in.is.*",
            "fields": "identifier,title,year",
            "count": batch,
        }
        if cursor:
            params["cursor"] = cursor

        url = f"{SCRAPE_URL}?{urllib.parse.urlencode(params)}"
        payload = json.loads(http_get(url, timeout=90).decode("utf-8"))

        items = payload.get("items", [])
        if not items:
            return

        yield items, payload.get("total")

        cursor = payload.get("cursor")
        if not cursor:
            return
        time.sleep(REQUEST_DELAY)


# Adopted international standards keep their origin's designation style:
# "IS/ISO/IEC 27001", "IS/ISO 10079-2", not "IS 10079 (Part 2)". The tokens
# stack, so `iso.iec` is IS/ISO/IEC and `iec.tr` is IS/IEC/TR.
_ADOPTION_TOKENS = {"iso": "ISO", "iec": "IEC", "ieee": "IEEE", "qc": "QC",
                    "pas": "PAS", "ts": "TS", "tr": "TR"}

# Single-letter tokens mark a language rendering of a standard that also
# exists in English: `b` bilingual, `h` Hindi. They are the same standard.
_VARIANT_TOKENS = {"b", "h"}


def _range(token: str) -> str:
    """`5-7` -> `5 to 7`; a plain token is returned unchanged."""
    return token.replace("-", " to ") if "-" in token else token


def parse_identifier(identifier: str) -> Optional[Dict[str, str]]:
    """Turn an archive identifier into an IS designation.

    `gov.in.is.2535.1.2004`        -> IS 2535 (Part 1):2004
    `gov.in.is.10026.3.1.1999`     -> IS 10026 (Part 3/Sec 1):1999
    `gov.in.is.10036.1-2.1982`     -> IS 10036 (Part 1 to 2):1982
    `gov.in.is.5000.od.1.1969`     -> IS 5000 (OD 1):1969
    `gov.in.is.iso.10079.2.1999`   -> IS/ISO 10079-2:1999
    `gov.in.is.iec.60079.20.1.2010`-> IS/IEC 60079-20-1:2010
    `gov.in.is.sp.15.1.1989`       -> SP 15 (Part 1):1989
    `gov.in.is.iso.iec.27001.2005` -> IS/ISO/IEC 27001:2005
    `gov.in.is.iso.105.A03.1993`   -> IS/ISO 105-A03:1993
    `gov.in.is.guide.43.2.1997`    -> IS/ISO/IEC Guide 43-2:1997
    `gov.in.is.1201-1220.1978`     -> IS 1201 to 1220:1978
    `gov.in.is.667.s.1981`         -> IS 667 (Supplement):1981
    `gov.in.is.1.b.1968`           -> IS 1:1968, marked as a language variant

    The first version of this parser accepted only `base[.part].year`, which
    silently skipped 1,826 genuine standards -- every multi-level part and
    every IS/ISO, IS/IEC and IS/QC adoption among them. Shapes it still does
    not recognise return None rather than a guessed designation.
    """
    match = re.match(r"^gov\.in\.is\.(.+)\.(\d{4})$", identifier)
    if not match:
        return None
    body, year = match.groups()
    tokens = body.split(".")

    adopted = False
    if tokens[0] == "sp":
        tokens.pop(0)
        prefix = "SP"
    elif tokens[0] == "guide":
        tokens.pop(0)
        prefix, adopted = "IS/ISO/IEC Guide", True
    else:
        origins = []
        while tokens and tokens[0] in _ADOPTION_TOKENS:
            origins.append(_ADOPTION_TOKENS[tokens.pop(0)])
        prefix = "IS/" + "/".join(origins) if origins else "IS"
        adopted = bool(origins)

    # A plain IS may cover a numbered run of standards in one document.
    base_pattern = r"\d+" if adopted else r"\d+(-\d+)?"
    if not tokens or not re.fullmatch(base_pattern, tokens[0]):
        return None
    base = _range(tokens.pop(0))

    variant = any(t in _VARIANT_TOKENS for t in tokens)
    supplement = "s" in tokens
    # `t` marks a Tentative Standard, designated "IS 17899 T".
    tentative = "t" in tokens
    tokens = [t for t in tokens if t not in _VARIANT_TOKENS and t not in {"s", "t"}]
    if tentative:
        base += " T"

    # Device-outline series ("od" + number) is part of the designation.
    qualifier = ""
    if tokens and tokens[0] == "od":
        tokens.pop(0)
        if tokens and re.fullmatch(r"\d+", tokens[0]):
            qualifier = f"OD {tokens.pop(0)}"
        else:
            return None
    if supplement:
        qualifier = "Supplement"

    if adopted:
        # International adoptions use the dash style of their origin, and
        # their parts may be lettered (ISO 105-A03).
        if any(not re.fullmatch(r"[A-Z]?\d+", t) for t in tokens):
            return None
        number = f"{prefix} {'-'.join([base] + tokens)}"
    else:
        if any(not re.fullmatch(r"\d+(-\d+)?", t) for t in tokens):
            return None
        number = f"{prefix} {base}"
        if tokens:
            part = f"Part {_range(tokens[0])}"
            if len(tokens) > 1:
                part += "/Sec " + "/".join(_range(t) for t in tokens[1:])
            number += f" ({part})"
        if qualifier:
            number += f" ({qualifier})"

    return {
        "number": f"{number}:{year}",
        "base": base,
        "part": tokens[0] if tokens else None,
        "year": year,
        "variant": variant,
    }


def clean_ocr(text: str) -> str:
    """Repair the OCR damage that would otherwise pollute the search index.

    These documents are scans. Left alone, "requirements regarding mater-ial"
    and "workmanship ann finish" end up in the embedding, so the worst
    recurring artifacts are corrected. This is deliberately conservative: it
    fixes mechanical damage, not wording.
    """
    # Hyphenation broken across a line: "mater-ial" -> "material".
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"(\w)-(\w{2,})", lambda m: m.group(0) if " " in m.group(0) else m.group(1) + m.group(2), text)

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Mojibake from the original encoding.
    for bad, good in (("�", ""), ("�", ""), ("~", ""), ("|", "I")):
        text = text.replace(bad, good)

    return text.strip()


# Clause 1 with its heading run into the text, as most OCR renderings have it:
# "1 SCOPE This standard prescribes ...", "1. Scope 1.1 This standard (Part 2)
# covers ...", up to the next numbered clause ("2 REFERENCES"). The clause
# must open the way scope clauses do, so a "1 Scope" inside a table or a
# later clause ("3.1 Scope The specimen shall ...") is not taken for it.
_INLINE_SCOPE = re.compile(
    r"(?:^|\s)1\s*\.?\s*(?:SCOPE|Scope)\s*[-:.—]*\s+"
    r"((?:\d\.\d(?:\.\d)?\s*)?(?:This|These)\s+(?:Indian\s+)?"
    r"(?:standard|code|specification|part|guide|method|International|Standard|test|terminology|glossary)\b"
    r".{30,2500}?)(?=\s+2\s*\.?\s+[A-Z][A-Za-z]{3,}|\Z)",
    re.DOTALL,
)


def extract_scope(text: str) -> Optional[str]:
    """Pull the SCOPE clause, which is what retrieval actually needs.

    BIS standards open with a numbered SCOPE clause stating what the standard
    covers. It is the single most useful paragraph for semantic search, far
    better than the title alone.
    """
    # The heading on a line of its own, then everything until the next
    # numbered clause heading.
    match = re.search(
        r"^\s*\d*\.?\s*SCOPE\s*\n(.{40,2500}?)(?=\n\s*\d+\.\s*[A-Z]{3,}|\n\s*[A-Z]{4,}\s*\n)",
        text,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if not match:
        # The heading run into the text. Without this, a third of the
        # collection fell through to the sentence search below, which takes
        # the first "This standard specifies ..." it meets, often in the
        # foreword: IS 10500 was searched as "the acceptable limits and the
        # permissible limits in the absence of alternate source" rather than
        # its scope, "requirements and the methods of sampling and test for
        # drinking water".
        match = _INLINE_SCOPE.search(text[:40000])
    if not match:
        # Fall back to a "This standard ..." sentence anywhere near the top.
        match = re.search(
            r"((?:This standard|This Indian Standard)\s+(?:covers|lays down|specifies|prescribes|deals with)[^.]{20,600}\.)",
            text[:12000],
            re.IGNORECASE,
        )
        if not match:
            return None

    scope = " ".join(match.group(1).split())
    scope = re.sub(r"^\d+\.\d+(?:\.\d+)?\s*", "", scope)  # drop a leading clause number

    # Keep the clause's opening statement, up to its first sub-clause. What
    # follows ("1.1.1 The standard also covers pipes for agricultural use.
    # 1.2 It does not cover ...") dilutes the statement in the index: with it,
    # IS 4985 scored 6.38 against "PVC pipe for drinking water supply" on the
    # cross-encoder, without it 7.13, and IS 2062 fell below a dimensions
    # standard for "structural steel plates and angles".
    # An opening too short to say anything ("This standard covers") keeps
    # what follows instead.
    opening = re.split(r"\s+\d+\.\d+(?:\.\d+)?\s+(?=[A-Z(])", scope, maxsplit=1)[0]
    if len(opening.strip()) >= 40:
        scope = opening

    # Stop at the next clause heading.
    #
    # The scope clause is followed by REFERENCES, TERMINOLOGY or similar, and
    # the patterns above sometimes run past it -- about 10% of a sample
    # carried "2 REFERENCES 2.1 The Indian Standard IS 4900..." into the
    # scope. Citation text in the embedding is noise: it makes a standard
    # about tea chests look partly like a standard about whatever it cites.
    scope = re.split(
        r"\s+\d+\s+(?:REFERENCES?|TERMINOLOGY|DEFINITIONS?|NORMATIVE|GENERAL|REQUIREMENTS?)\b",
        scope,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    # Footnote markers that OCR leaves inline, e.g. "*Specification for ..."
    scope = re.split(r"\s+[*f†]\s*(?=[A-Z])", scope, maxsplit=1)[0]

    scope = scope.strip()

    if len(scope) < 40:
        return None
    return scope[:1200]


def classify(title: str, scope: str) -> Optional[str]:
    """Assign a sector, or None if nothing matches confidently."""
    haystack = f"{title} {scope}".lower()
    for sector, pattern in SECTOR_RULES:
        if re.search(pattern, haystack, re.IGNORECASE):
            return sector
    return None


def fetch_text(identifier: str) -> Optional[str]:
    """The plain-text rendering of one standard, cached on disk."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{identifier}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8", errors="replace")

    try:
        metadata = json.loads(http_get(METADATA_URL.format(identifier=identifier)).decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None

    name = next(
        (
            f["name"]
            for f in metadata.get("files", [])
            if f["name"].endswith(".txt") and not f["name"].endswith("_meta.txt")
        ),
        None,
    )
    if not name:
        return None

    try:
        raw = http_get(DOWNLOAD_URL.format(identifier=identifier, filename=urllib.parse.quote(name)))
    except (urllib.error.URLError, OSError):
        return None

    text = raw.decode("utf-8", errors="replace")
    cached.write_text(text, encoding="utf-8")
    return text


def title_from_search(raw_title: str) -> str:
    """'IS 2925: Specification for Industrial Safety Helmets(Bi-Lingual)'."""
    title = re.sub(r"^IS\s*[\d.\-]+\s*:\s*", "", str(raw_title)).strip()
    title = re.sub(r"\(\s*Bi-?Lingual\s*\)", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\s{2,}", " ", title)
    return title


def rescope() -> int:
    """Re-run scope extraction over the cached texts of every ingested record.

    For when the extractor improves: the texts are already on disk, so there
    is nothing to fetch. Number, title and identifier are kept; scope,
    provenance and sector become what a fresh ingest would now give them.
    """
    from collections import Counter

    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    changes = Counter()
    wrong_text = misfiled()
    for record in payload["standards"]:
        cached = CACHE_DIR / f"{record['identifier']}.txt"
        if not cached.exists():
            changes["no cached text"] += 1
            continue
        if record["identifier"] in wrong_text:
            scope = ""
        else:
            scope = extract_scope(clean_ocr(cached.read_text(encoding="utf-8", errors="replace"))) or ""
        old = record.get("scope") or ""
        sector = classify(record["title"], scope) or "general"
        if sector != record.get("category"):
            changes["sector changed"] += 1
            record["category"] = sector
        if scope == old:
            changes["unchanged"] += 1
            continue
        changes["scope found" if not old else "scope lost" if not scope else "scope changed"] += 1
        record["scope"] = scope
        record["provenance"] = "published_text_ocr" if scope else "number_and_title_only"
        record["category"] = classify(record["title"], scope) or "general"
    payload["_meta"]["rescoped"] = time.strftime("%Y-%m-%d")
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rescoped {len(payload['standards'])} records: {dict(changes)} -> {OUTPUT}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=600, help="how many standards to keep")
    parser.add_argument("--scan", type=int, default=4000, help="how many archive records to consider")
    parser.add_argument(
        "--overfetch",
        type=float,
        default=3.0,
        help="candidates fetched per standard kept; many yield no usable record",
    )
    parser.add_argument("--list", action="store_true", help="list candidates without fetching text")
    parser.add_argument(
        "--rescope",
        action="store_true",
        help="re-extract every ingested record's scope from the cached texts, without fetching",
    )
    args = parser.parse_args()
    if args.rescope:
        return rescope()

    print(f"scanning up to {args.scan} archive records for standards in our sectors...")

    # Keyed by designation. A bilingual or Hindi rendering of a standard shares
    # its number with the English edition; the English one is preferred
    # because its text is what the OCR and scope extraction can read.
    by_number: Dict[str, dict] = {}
    unparsed = 0
    total = None

    for items, reported_total in scrape_all():
        if total is None:
            total = reported_total
            print(f"  collection holds {total} standards", flush=True)

        for doc in items:
            parsed = parse_identifier(doc.get("identifier", ""))
            if not parsed:
                unparsed += 1
                continue
            title = title_from_search(doc.get("title", ""))
            if not title:
                continue
            existing = by_number.get(parsed["number"])
            if existing and not (existing["variant"] and not parsed["variant"]):
                continue
            by_number[parsed["number"]] = {**parsed, "identifier": doc["identifier"], "title": title}

        print(f"  scanned: {len(by_number)} unique standards, {unparsed} unparsed", flush=True)

        if len(by_number) >= args.scan:
            break

    # Glossaries and vocabularies used to be excluded here as "not things a
    # procurement officer specifies". They are published Indian Standards all
    # the same, and a corpus described as the full collection should hold
    # them; the confidence gate, not a title filter, decides what is shown as
    # a recommendation.
    candidates: List[dict] = list(by_number.values())
    print(f"  {len(candidates)} candidates; {unparsed} identifiers in no recognised shape")

    # Keep only those whose title already suggests one of our sectors; the
    # scope check happens after the text is fetched.
    # Title-matched candidates first, then the rest.
    #
    # The title pre-filter used to be the whole selection, which quietly
    # capped the corpus: "Male stud tee bodies" names no sector, but its
    # scope clause does, and the record was discarded before its text was
    # ever fetched. Titles that already match are still fetched first --
    # they have the best hit rate -- but the others are no longer excluded.
    titled = [c for c in candidates if classify(c["title"], "")]
    untitled = [c for c in candidates if not classify(c["title"], "")]
    targeted = titled + untitled
    print(f"\n{len(targeted)} of {len(candidates)} candidates fall in our sectors")

    if args.list:
        for item in targeted[:40]:
            print(f"  {item['number']:<22} {item['title'][:62]}")
        print(f"  ... ({len(targeted)} total)")
        return 0

    print(f"fetching text for up to {args.limit} (cached after first run)...\n")

    ingested: List[dict] = []
    no_scope = 0
    no_text = 0
    done = 0

    def process(item: dict) -> Optional[dict]:
        """Fetch and parse one standard. Returns None when unusable."""
        text = fetch_text(item["identifier"])
        if not text:
            return {"_skip": "no_text"}

        cleaned = clean_ocr(text)
        scope = extract_scope(cleaned)

        # A record with no extractable SCOPE clause is kept, not discarded.
        # Its IS number and title are real, so it stays findable by both, and
        # roughly a third of the collection is in this state -- dropping them
        # excluded thousands of genuine standards. The weaker evidence is
        # recorded in `provenance` rather than papered over, and no scope text
        # is ever invented to fill the gap.
        record_provenance = "published_text_ocr" if scope else "number_and_title_only"

        # Without a scope clause the title is all the classifier has.
        #
        # A standard no sector rule recognises is kept as `general`, not
        # discarded. Dropping them removed ~6,000 genuine standards
        # (mountaineering ascenders, insulating varnishes, pigment
        # dispersions...) for the sole reason that the regex taxonomy had no
        # pattern for their subject. The sector is a browsing aid; search runs
        # on the text either way, and `general` says plainly that no sector
        # was assigned rather than guessing one.
        sector = classify(item["title"], scope or "") or "general"

        return {
            "number": item["number"],
            "title": item["title"],
            "scope": scope or "",
            "category": sector,
            "version": item["year"],
            "identifier": item["identifier"],
            "provenance": record_provenance,
            "source_url": f"https://archive.org/details/{item['identifier']}",
        }

    # Fetching dominates the runtime and is almost entirely network wait, so
    # a small thread pool turns hours into minutes without straining the host.
    pool = targeted[: int(args.limit * args.overfetch)]
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(process, item): item for item in pool}
        for future in as_completed(futures):
            done += 1
            try:
                result = future.result()
            except Exception:
                no_text += 1
                continue

            if result is None or "_skip" in result:
                reason = (result or {}).get("_skip")
                if reason == "no_text":
                    no_text += 1
                elif reason == "no_scope":
                    no_scope += 1
                continue

            ingested.append(result)
            if len(ingested) % 100 == 0:
                print(f"  {len(ingested)} ingested ({done} examined)", flush=True)
                # Checkpoint: a run over thousands of documents must not lose
                # everything to one interruption.
                _write_output(ingested, partial=True)

            if len(ingested) >= args.limit:
                break

    ingested.sort(key=lambda r: r["number"])

    _write_output(ingested)

    from collections import Counter

    print()
    print(f"ingested        : {len(ingested)}")
    print(f"  no text file  : {no_text}")
    print(f"  no scope found: {no_scope}")
    _prov = Counter(r.get("provenance", "published_text_ocr") for r in ingested)
    print(f"  with scope    : {_prov.get('published_text_ocr', 0)}")
    print(f"  title only    : {_prov.get('number_and_title_only', 0)}")
    for sector, count in sorted(Counter(s["category"] for s in ingested).items()):
        print(f"  {sector:<28} {count:>4}")
    print()
    print(f"wrote {OUTPUT.relative_to(_REPO_ROOT)}")
    return 0


def _write_output(ingested: List[dict], partial: bool = False) -> None:
    """Persist what has been ingested so far."""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "_meta": {
                    "source": "https://archive.org/, gov.in.is.* collection (Public.Resource.Org)",
                    "retrieved": time.strftime("%Y-%m-%d"),
                    "provenance": "published_text_ocr",
                    "provenance_meaning": (
                        "IS number, title and SCOPE clause are taken from the published "
                        "standard. The text is OCR of a scanned document, so it contains "
                        "recognition errors. It is the real scope clause, not written text."
                    ),
                    "count": len(ingested),
                    "partial": partial,
                },
                "standards": ingested,
            },
            indent=2,
            ensure_ascii=False,
        )
        + chr(10),
        encoding="utf-8",
    )


if __name__ == "__main__":
    sys.exit(main())
