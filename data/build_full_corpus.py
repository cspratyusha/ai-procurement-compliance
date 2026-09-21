"""Build the full corpus from archive-ingested standards plus curated records.

This produces `data/standards_corpus_full.json`, the corpus the engine should
actually serve. Records come from three populations, and the difference
between them matters enough to record on every record:

  published_text_ocr        IS number, title and SCOPE clause taken from the
                            published standard (via the Public.Resource.Org
                            archive). OCR of a scan, so imperfect text, but it
                            is the real scope clause.
  number_and_title_referenced
                            IS number and title from a public reference list;
                            scope written from the title.
  consolidated              the original pilot data; realistic but unverified
                            throughout.

Curated records win over ingested ones for the same IS number, because the
curated set is what the certification, amendment and relationship data is
keyed to. Their scope text is weaker, but breaking those links would lose
more than it gains.

Run with::

    python data/build_full_corpus.py --check
    python data/build_full_corpus.py
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

CURATED = _REPO_ROOT / "data" / "standards_corpus_expanded.json"
INGESTED = _REPO_ROOT / "data" / "archive" / "ingested_standards.json"
OUTPUT = _REPO_ROOT / "data" / "standards_corpus_full.json"

SECTOR_PREFIX = {
    "electrical_cables": "ELEC",
    "electrical_installations": "ELECINST",
    "cement_building_materials": "CEM",
    "steel_pipes_fittings": "STEEL",
    "plastic_pipes": "PIPE",
    "structural_steel": "STRUCT",
    "ppe": "PPE",
    "geotechnical": "GEO",
    "water_quality": "WATER",
    "textiles": "TEX",
    "timber_furniture": "TIMB",
    "machinery_equipment": "MACH",
    "chemicals": "CHEM",
    "food_agriculture": "FOOD",
    "packaging": "PACK",
    "rubber_leather": "RUB",
    "measurement_testing": "TEST",
}

# Scope text shorter than this is not worth embedding.
MIN_SCOPE_CHARS = 60

# OCR noise that survives cleaning. A scope where these dominate is unusable.
_NOISE = re.compile(r"[^\x20-\x7E]")


def normalize(number: str) -> str:
    text = " ".join(number.strip().split())
    text = re.sub(r"\(\s*part\s*", "(Part ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\)", ")", text)
    text = re.sub(r"\s*:\s*", ":", text)
    return text


def family(number: str) -> str:
    return normalize(number).split(":")[0].upper()


def usable_scope(scope: str) -> bool:
    """Reject scope text too short or too OCR-damaged to search on."""
    if len(scope) < MIN_SCOPE_CHARS:
        return False
    noise = len(_NOISE.findall(scope))
    return noise / max(len(scope), 1) < 0.05


def keywords_from(title: str, scope: str) -> list:
    """A few salient terms for the BM25 half of the index.

    Derived rather than authored: the title already carries the terms a user
    is most likely to type.
    """
    stop = {
        "the", "for", "and", "with", "of", "in", "to", "a", "an", "its", "on",
        "specification", "code", "practice", "methods", "method", "test",
        "part", "indian", "standard", "requirements", "general", "use", "used",
        "this", "shall", "are", "is", "be", "by", "or", "from", "covers",
    }
    words = re.findall(r"[a-zA-Z][a-zA-Z-]{3,}", f"{title} {scope[:300]}".lower())
    seen = []
    for word in words:
        if word in stop or word in seen:
            continue
        seen.append(word)
        if len(seen) >= 10:
            break
    return seen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only; write nothing")
    args = parser.parse_args()

    curated = json.loads(CURATED.read_text(encoding="utf-8"))
    if not INGESTED.exists():
        raise SystemExit(
            f"{INGESTED} not found. Run data/ingest_archive.py first."
        )
    payload = json.loads(INGESTED.read_text(encoding="utf-8"))
    ingested = payload["standards"]
    ingest_provenance = payload["_meta"]["provenance"]

    merged = []
    seen = set()

    # Curated first: they carry the certification and relationship links.
    for record in curated:
        key = normalize(record["number"])
        seen.add(key)
        merged.append({**record, "number": key})

    kept = 0
    rejected_scope = 0
    duplicate = 0

    for item in ingested:
        key = normalize(item["number"])
        if key in seen:
            duplicate += 1
            continue
        if not usable_scope(item["scope"]):
            rejected_scope += 1
            continue

        sector = item["category"]
        if sector not in SECTOR_PREFIX:
            continue

        seen.add(key)
        kept += 1
        merged.append(
            {
                "number": key,
                "title": item["title"],
                "scope": item["scope"],
                # Ingested records have no separate description; the scope
                # clause is the authoritative text and stands on its own.
                "description": "",
                "category": sector,
                "family": family(key),
                "version": item.get("version", ""),
                "last_amended": "",
                "status": "active",
                "superseded_by_number": None,
                "keywords": keywords_from(item["title"], item["scope"]),
                "sources": ["archive.org/gov.in.is"],
                "source_url": item.get("source_url"),
                "verified": False,
                "provenance": ingest_provenance,
            }
        )

    merged.sort(key=lambda r: (r["category"], r["number"]))
    counters: Counter = Counter()
    for record in merged:
        prefix = SECTOR_PREFIX[record["category"]]
        counters[prefix] += 1
        record["id"] = f"IS-{prefix}-{counters[prefix]:04d}"

    by_sector = Counter(r["category"] for r in merged)
    by_provenance = Counter(r.get("provenance", "unknown") for r in merged)

    print(f"curated in    : {len(curated)}")
    print(f"ingested in   : {len(ingested)}")
    print(f"  kept        : {kept}")
    print(f"  duplicate   : {duplicate} (curated record kept)")
    print(f"  bad scope   : {rejected_scope}")
    print(f"\nfull corpus   : {len(merged)} standards across {len(by_sector)} sectors")
    for sector, count in sorted(by_sector.items()):
        print(f"  {sector:<28} {count:>4}")
    print("provenance:")
    for source, count in sorted(by_provenance.items()):
        print(f"  {source:<32} {count:>4}")

    problems = []
    for label, values in (
        ("number", [r["number"] for r in merged]),
        ("id", [r["id"] for r in merged]),
    ):
        duplicates = [v for v, n in Counter(values).items() if n > 1]
        if duplicates:
            problems.append(f"duplicate {label}s: {duplicates[:5]}")
    for record in merged:
        if not record["title"].strip():
            problems.append(f"{record['number']}: empty title")
        if not record["scope"].strip():
            problems.append(f"{record['number']}: empty scope")

    if problems:
        print(f"\nVALIDATION FAILED ({len(problems)}):")
        for problem in problems[:10]:
            print(f"  - {problem}")
        return 1

    print("\nvalidation: OK")

    if args.check:
        print("(--check: nothing written)")
        return 0

    OUTPUT.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUTPUT.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
