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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = _REPO_ROOT / "data" / "archive" / "ingested_standards.json"
CACHE_DIR = _REPO_ROOT / "data" / "archive" / "cache"

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{identifier}"
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"

USER_AGENT = "ai-compliance-sih/1.0 (standards retrieval research; contact via repo)"

# Be a good citizen: archive.org is a donation-funded public service.
REQUEST_DELAY = 0.6

# Sector classification. Order matters — the first pattern that matches wins,
# so put specific categories before general ones.
#
# These map onto the sectors the existing corpus already uses, so curated
# certification and relationship data keeps working against the new records.
SECTOR_RULES = [
    ("electrical_cables", r"\bcable|\bconductor|\bwire\b|flexible cord|sheathed"),
    ("electrical_installations", r"electrical installation|wiring|switchgear|switches for|socket|\bearthing|luminaire|lighting"),
    ("cement_building_materials", r"\bcement|concrete|aggregate|\bbrick|mortar|masonry|plaster|\blime\b|pozzolana|fly ash|admixture"),
    ("steel_pipes_fittings", r"steel tube|steel pipe|\btubular|pipe fitting|ductile iron pipe|\bflange"),
    ("plastic_pipes", r"polyethylene pipe|\bPVC pipe|unplasticized|\bHDPE|\bUPVC|plastic pipe|water bar"),
    ("structural_steel", r"structural steel|\brolled steel|reinforcement|deformed bar|\bjoist|\bangle|\bbeam\b|prestress|welding"),
    ("ppe", r"safety helmet|protective|personal protective|safety footwear|respirator|\bglove|\bgoggle|ear muff|safety belt"),
    ("geotechnical", r"\bsoil\b|geotechnical|foundation|bearing capacity|\bpile\b|earthwork|subgrade"),
    ("water_quality", r"drinking water|water quality|wastewater|sewage|\beffluent|water supply|potable"),
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


def search(rows: int, page: int) -> List[dict]:
    """One page of the gov.in.is.* collection."""
    params = urllib.parse.urlencode(
        {
            "q": "identifier:gov.in.is.*",
            "fl[]": "identifier",
            "rows": rows,
            "page": page,
            "output": "json",
            "sort[]": "identifier asc",
        },
        doseq=True,
    )
    # fl[] repeats, so build it manually to request several fields.
    params = params.replace("fl%5B%5D=identifier", "fl%5B%5D=identifier&fl%5B%5D=title&fl%5B%5D=year")
    payload = json.loads(http_get(f"{SEARCH_URL}?{params}").decode("utf-8"))
    return payload["response"]["docs"]


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
    page = 1
    rows = 500

    while len(candidates) < args.scan:
        try:
            docs = search(rows, page)
        except Exception as exc:
            print(f"  search page {page} failed: {exc}")
            break
        if not docs:
            break

        for doc in docs:
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

        print(f"  page {page}: {len(candidates)} candidates so far")
        page += 1
        time.sleep(REQUEST_DELAY)
        if page > 40:
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

    for index, item in enumerate(targeted):
        if len(ingested) >= args.limit:
            break

        text = fetch_text(item["identifier"])
        if not text:
            no_text += 1
            continue

        cleaned = clean_ocr(text)
        scope = extract_scope(cleaned)
        if not scope:
            no_scope += 1
            continue

        sector = classify(item["title"], scope)
        if not sector:
            continue

        ingested.append(
            {
                "number": item["number"],
                "title": item["title"],
                "scope": scope,
                "category": sector,
                "version": item["year"],
                "identifier": item["identifier"],
                "source_url": f"https://archive.org/details/{item['identifier']}",
            }
        )

        if len(ingested) % 25 == 0:
            print(f"  {len(ingested)} ingested ({index + 1} examined)")
        time.sleep(REQUEST_DELAY)

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
                },
                "standards": ingested,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    from collections import Counter

    print(f"\ningested        : {len(ingested)}")
    print(f"  no text file  : {no_text}")
    print(f"  no scope found: {no_scope}")
    for sector, count in sorted(Counter(s["category"] for s in ingested).items()):
        print(f"  {sector:<28} {count:>4}")
    print(f"\nwrote {OUTPUT.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
