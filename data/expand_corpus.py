"""Expand the canonical corpus with additional Indian Standards.

The retrieval pipeline was built and tuned against 45 standards. That is small
enough that retrieval is an easy problem, which is why the accuracy figures in
MODEL_AND_EVALUATION.md carry a scope warning. Growing the corpus is the
single biggest quality lever available, and it is a data exercise rather than
an engineering one.

Provenance is tracked per record, because the two sources are not equally
trustworthy:

  consolidated              from the original three datasets; realistic but
                            unverified, scope text invented
  number_and_title_referenced
                            IS number and title taken from a public reference
                            list of standards actually cited in Indian civil
                            engineering practice; scope written from the title,
                            NOT copied from the paywalled standard

Neither is authoritative. The second is better, because at least the number
and title correspond to a standard that really exists under that designation.

Run with::

    python data/expand_corpus.py --check    # report, write nothing
    python data/expand_corpus.py            # write the expanded corpus
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

BASE = _REPO_ROOT / "data" / "standards_corpus.json"
EXPANSION = _REPO_ROOT / "data" / "expansion" / "expansion_source.json"
OUTPUT = _REPO_ROOT / "data" / "standards_corpus_expanded.json"

# Sector prefixes for generated ids; mirrors data/consolidate.py.
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
}


def normalize(number: str) -> str:
    text = " ".join(number.strip().split())
    text = re.sub(r"\(\s*part\s*", "(Part ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\)", ")", text)
    text = re.sub(r"\s*:\s*", ":", text)
    return text


def family(number: str) -> str:
    return normalize(number).split(":")[0].upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only; write nothing")
    args = parser.parse_args()

    base = json.loads(BASE.read_text(encoding="utf-8"))
    payload = json.loads(EXPANSION.read_text(encoding="utf-8"))
    additions = payload["standards"]
    provenance = payload["_meta"]["provenance"]

    existing = {normalize(s["number"]) for s in base}

    # Carry forward the base corpus, tagging its provenance so the two
    # populations stay distinguishable after the merge.
    merged = []
    for record in base:
        merged.append({**record, "provenance": record.get("provenance", "consolidated")})

    skipped = []
    for item in additions:
        key = normalize(item["number"])
        if key in existing:
            skipped.append(item["number"])
            continue
        existing.add(key)

        category = item["category"]
        if category not in SECTOR_PREFIX:
            raise SystemExit(
                f"{item['number']}: unknown category {category!r}. "
                "Add it to SECTOR_PREFIX so ids can be generated."
            )

        merged.append(
            {
                "number": key,
                "title": item["title"],
                "scope": item["scope"],
                "description": item["description"],
                "category": category,
                "family": family(key),
                "version": item.get("version", ""),
                "last_amended": "",
                "status": item.get("status", "active"),
                "superseded_by_number": None,
                "keywords": item.get("keywords", []),
                "sources": ["expansion"],
                "verified": False,
                "provenance": provenance,
            }
        )

    # Deterministic order, then renumber ids per sector.
    merged.sort(key=lambda r: (r["category"], r["number"]))
    counters: Counter = Counter()
    for record in merged:
        prefix = SECTOR_PREFIX[record["category"]]
        counters[prefix] += 1
        record["id"] = f"IS-{prefix}-{counters[prefix]:03d}"

    # Report
    by_category = Counter(r["category"] for r in merged)
    by_provenance = Counter(r["provenance"] for r in merged)

    print(f"base corpus      : {len(base)}")
    print(f"additions        : {len(additions)} ({len(skipped)} already present)")
    if skipped:
        print(f"  skipped        : {', '.join(skipped)}")
    print(f"expanded corpus  : {len(merged)} standards across {len(by_category)} sectors")
    for category, count in sorted(by_category.items()):
        print(f"  {category:<28} {count:>3}")
    print("provenance:")
    for source, count in sorted(by_provenance.items()):
        print(f"  {source:<32} {count:>3}")

    # Validation
    problems = []
    numbers = [r["number"] for r in merged]
    ids = [r["id"] for r in merged]
    for label, values in (("number", numbers), ("id", ids)):
        duplicates = [v for v, n in Counter(values).items() if n > 1]
        if duplicates:
            problems.append(f"duplicate {label}s: {duplicates}")
    for record in merged:
        if not record["title"].strip():
            problems.append(f"{record['number']}: empty title")
        if not record["scope"].strip():
            problems.append(f"{record['number']}: empty scope")

    if problems:
        print(f"\nVALIDATION FAILED ({len(problems)}):")
        for problem in problems:
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
