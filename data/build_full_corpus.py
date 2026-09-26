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
    # Sectors added when the ingest filters were relaxed. Without a prefix
    # here a record is silently dropped at id-assignment, so this map has to
    # track SECTOR_RULES in data/ingest_archive.py.
    "electronics_telecom": "ELECTRONIC",
    "metals_alloys": "METAL",
    "paints_coatings": "PAINT",
    "petroleum_lubricants": "PETRO",
    "refractories_ceramics": "REFRAC",
    "mechanical_fittings": "FITTING",
    "paper_printing": "PAPER",
    "automotive": "AUTO",
    "medical_laboratory": "MEDLAB",
    # Standards no sector rule recognised. Kept rather than dropped; see the
    # classification note in data/ingest_archive.py.
    "general": "GEN",
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


def tidy_scope(scope: str) -> str:
    """Trim a scope clause that ran past its own section.

    The extractor truncates at the next clause heading, but records ingested
    before that fix carry citation text — "...plywood teachests. 2 REFERENCES
    2.1 The Indian Standard IS 4900...". Rather than re-fetch thousands of
    documents, the same truncation is applied here at merge time, so the
    corpus is clean regardless of when a record was parsed.
    """
    scope = re.split(
        r"\s+\d+\s+(?:REFERENCES?|TERMINOLOGY|DEFINITIONS?|NORMATIVE|GENERAL|REQUIREMENTS?)\b",
        scope,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    scope = re.split(r"\s+[*f†]\s*(?=[A-Z])", scope, maxsplit=1)[0]
    # A leading clause number or stray punctuation left by OCR.
    scope = re.sub(r"^[.\s]*\d+(\.\d+)*\s*", "", scope)
    return scope.strip()


def usable_scope(scope: str) -> bool:
    """Reject scope text too short or too OCR-damaged to search on."""
    if len(scope) < MIN_SCOPE_CHARS:
        return False
    noise = len(_NOISE.findall(scope))
    return noise / max(len(scope), 1) < 0.05


def _edition_year(number: str) -> int:
    match = re.search(r":(\d{4})$", number)
    return int(match.group(1)) if match else 0


def mark_superseded_editions(records: list) -> int:
    """Mark an archive edition superseded when the corpus holds a newer one.

    The archive publishes every edition it has, so one standard can arrive
    three times (IS 269:1989, :2013, :2015). Left as-is, all three read as
    "Current" everywhere the stored status is shown. A later edition of the
    same designation replaces the earlier one, so each older archive edition
    is marked superseded and pointed at the newest edition present.

    Only archive-sourced records are changed. Curated records carry
    researched status that this inference must never overwrite -- an
    archive record can be superseded by a curated one, not the reverse.
    Returns how many records were marked.
    """
    by_family: dict = {}
    for record in records:
        by_family.setdefault(family(record["number"]), []).append(record)

    marked = 0
    for editions in by_family.values():
        if len(editions) < 2:
            continue
        newest = max(editions, key=lambda r: _edition_year(r["number"]))
        newest_year = _edition_year(newest["number"])
        for record in editions:
            if record is newest or "archive.org/gov.in.is" not in record.get("sources", []):
                continue
            if record.get("status") != "active" or _edition_year(record["number"]) >= newest_year:
                continue
            record["status"] = "superseded"
            record["superseded_by_number"] = newest["number"]
            marked += 1
    return marked


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
        item = {**item, "scope": tidy_scope(item.get("scope") or "")}

        # A record the ingest marked title-only has no scope clause by
        # definition, and rejecting it for that would re-impose the filter
        # the ingest was changed to drop. Its IS number and title are real,
        # so it stays searchable on those; the weaker evidence travels with
        # the record as `provenance` rather than being hidden.
        title_only = item.get("provenance") == "number_and_title_only"
        if not title_only and not usable_scope(item["scope"]):
            # Too short or too OCR-damaged to embed. The record used to be
            # dropped outright, losing a real standard over bad scan quality;
            # it is now kept on its number and title, exactly like a record
            # whose scope was never found, and labelled the same way.
            rejected_scope += 1
            item = {**item, "scope": "", "provenance": "number_and_title_only"}

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
                # Per-record, not per-file: one ingest run now produces both
                # scope-bearing and title-only records, and collapsing them to
                # a single file-level label would overstate the weaker half.
                "provenance": item.get("provenance", ingest_provenance),
            }
        )

    superseded_editions = mark_superseded_editions(merged)

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
    print(f"  bad scope   : {rejected_scope} (kept on number and title)")
    print(f"  superseded  : {superseded_editions} older editions of a standard the corpus also holds newer")
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
        # A title-only record has no scope clause by definition -- that is
        # what its provenance records. Flagging it as a defect would fail
        # every run, and "fixing" it by writing scope text would invent the
        # very thing the provenance says was never found.
        if (
            not record["scope"].strip()
            and record.get("provenance") != "number_and_title_only"
        ):
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

    if remap_query_sets(merged):
        return 1
    return 0


QUERY_SETS = [
    _REPO_ROOT / "data" / "eval_set_full.json",
    _REPO_ROOT / "data" / "train_queries_full.json",
]


def remap_query_sets(corpus: list) -> int:
    """Re-point the full-corpus query sets at the ids this build assigned.

    Ids are positional within a sector, so every rebuild that adds records
    shifts them. A query set left on the old ids silently labels the wrong
    standard as correct -- the accuracy test then measures nonsense, and a
    ranker trained on it learns it (PROGRESS.md, Phase D: CV 0.93, held-out
    0.24). Each entry also stores `correct_number`, which is stable, so the
    id is re-derived from it here on every write.

    Returns the number of entries whose standard is no longer in the corpus.
    """
    by_number = {r["number"]: r for r in corpus}
    lost_total = 0
    for path in QUERY_SETS:
        if not path.exists():
            continue
        items = json.loads(path.read_text(encoding="utf-8"))
        changed = 0
        lost = []
        for item in items:
            record = by_number.get(normalize(item["correct_number"]))
            if record is None:
                lost.append(item["correct_number"])
                continue
            # A query labelled with an edition the corpus now holds a newer
            # edition of has the newer one as its right answer: that is what
            # a tender should cite, and the ranker deliberately prefers it.
            # Leaving the old label scored the engine wrong for ranking the
            # current edition first (9 of 60 sampled "misses" were exactly
            # this, each with the newer edition at rank 1).
            newer = by_number.get(record.get("superseded_by_number") or "")
            if record.get("status") == "superseded" and newer is not None:
                record = newer
                item["correct_number"] = newer["number"]
            if item["correct_id"] != record["id"] or item.get("category") != record["category"]:
                changed += 1
            item["correct_id"] = record["id"]
            item["category"] = record["category"]
        path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"remapped {path.name}: {changed} of {len(items)} ids updated", end="")
        print(f", {len(lost)} standards missing: {lost[:5]}" if lost else "")
        lost_total += len(lost)
    return lost_total


if __name__ == "__main__":
    sys.exit(main())
