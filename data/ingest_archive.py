"""Ingest Indian Standards from the Public.Resource.Org archive.

The pilot corpus was placeholder data: realistic IS numbers with scope text we
wrote ourselves. This replaces that with the **published scope clause of the
actual standard**, which is the difference between a demo and a usable tool.

Source: the `gov.in.is.*` collection on archive.org — 22,022 Indian Standards
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
]

# Standards we do not want: management-system, vocabulary-only and
# administrative documents are not things a procurement officer specifies.
EXCLUDE_TITLE = re.compile(
    r"glossary of terms|vocabulary|\bcode of ethics|guidelines for the preparation",
    re.IGNORECASE,
)


def http_get(url: str, timeout: int = 45) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def scrape_all(batch: int = 1000):
    """Yield every item in the collection, via the cursor-based scrape API.

    `advancedsearch` cannot page past 10,000 results — it is Solr underneath,
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


def parse_identifier(identifier: str) -> Optional[Dict[str, str]]:
    """`gov.in.is.2535.1.2004` -> number 'IS 2535 (Part 1)', year '2004'.

    Returns None for identifiers that do not fit the pattern, rather than
    guessing at a shape we do not recognise.
    """
    match = re.match(r"^gov\.in\.is\.(\d+)(?:\.(\d+))?\.(\d{4})$", identifier)
    if not match:
        return None

    base, part, year = match.groups()
    number = f"IS {base}"
    if part:
        number += f" (Part {part})"
    return {"number": f"{number}:{year}", "base": base, "part": part, "year": year}


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


def extract_scope(text: str) -> Optional[str]:
    """Pull the SCOPE clause, which is what retrieval actually needs.

    BIS standards open with a numbered SCOPE clause stating what the standard
    covers. It is the single most useful paragraph for semantic search, far
    better than the title alone.
    """
    # The heading, then everything until the next numbered clause heading.
    match = re.search(
        r"^\s*\d*\.?\s*SCOPE\s*\n(.{40,2500}?)(?=\n\s*\d+\.\s*[A-Z]{3,}|\n\s*[A-Z]{4,}\s*\n)",
        text,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
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
    scope = re.sub(r"^\d+\.\d+\s*", "", scope)  # drop a leading clause number

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=600, help="how many standards to keep")
    parser.add_argument("--scan", type=int, default=4000, help="how many archive records to consider")
    parser.add_argument("--list", action="store_true", help="list candidates without fetching text")
    args = parser.parse_args()

    print(f"scanning up to {args.scan} archive records for standards in our sectors...")

    candidates: List[dict] = []
    seen_numbers = set()
    total = None

    for items, reported_total in scrape_all():
        if total is None:
            total = reported_total
            print(f"  collection holds {total} standards", flush=True)

        for doc in items:
            parsed = parse_identifier(doc.get("identifier", ""))
            if not parsed:
                continue
            if parsed["number"] in seen_numbers:
                continue
            title = title_from_search(doc.get("title", ""))
            if not title or EXCLUDE_TITLE.search(title):
                continue
            seen_numbers.add(parsed["number"])
            candidates.append({**parsed, "identifier": doc["identifier"], "title": title})

        if len(candidates) % 5000 < 1000:
            print(f"  scanned: {len(seen_numbers)} unique, {len(candidates)} candidates", flush=True)

        if len(candidates) >= args.scan:
            break

    # Keep only those whose title already suggests one of our sectors; the
    # scope check happens after the text is fetched.
    targeted = [c for c in candidates if classify(c["title"], "")]
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
        if not scope:
            return {"_skip": "no_scope"}

        sector = classify(item["title"], scope)
        if not sector:
            return {"_skip": "no_sector"}

        return {
            "number": item["number"],
            "title": item["title"],
            "scope": scope,
            "category": sector,
            "version": item["year"],
            "identifier": item["identifier"],
            "source_url": f"https://archive.org/details/{item['identifier']}",
        }

    # Fetching dominates the runtime and is almost entirely network wait, so
    # a small thread pool turns hours into minutes without straining the host.
    pool = targeted[: args.limit * 3]  # over-fetch: many will lack a scope clause
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
                    "source": "https://archive.org/ — gov.in.is.* collection (Public.Resource.Org)",
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
