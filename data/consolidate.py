"""Merge the project's three standards datasets into one canonical corpus.

Background
----------
The repository grew three overlapping datasets, built independently:

  A. ``standards-retrieval/data/mock_corpus.json``  (30 records, ids ``IS-ELEC-001``)
  B. ``data/raw/standards.json``                    (18 records, ids ``std_001``)
  C. ``data/seed_standards.json``                   (10 records, different schema)

They share only three IS numbers between A and B, use different id schemes,
and use different category vocabularies (``Electrical Cables & Wires`` vs
``electrical_cables``). C is almost entirely a subset of B.

This script merges them into ``data/standards_corpus.json``, keyed by IS
number, with one id scheme and one category vocabulary.

Merge rules
-----------
* **Identity** is the IS number, normalized (case, spacing, ``Part`` casing).
* **On conflict**, the record with the richer ``scope`` + ``description`` wins,
  because the retrieval pipeline embeds those fields. A's records are
  consistently longer and written for semantic search, so A usually wins.
* **Category** is mapped onto one snake_case vocabulary.
* **Status** (``active`` / ``superseded``) is preserved: the post-processing
  stage derives supersession penalties from it.
* Provenance is recorded per record in ``sources`` so the merge is auditable.

Run with::

    python data/consolidate.py            # writes data/standards_corpus.json
    python data/consolidate.py --check    # validate only, no write
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE_A = _REPO_ROOT / "standards-retrieval" / "data" / "mock_corpus.json"
SOURCE_B = _REPO_ROOT / "data" / "raw" / "standards.json"
SOURCE_C = _REPO_ROOT / "data" / "seed_standards.json"
OUTPUT = _REPO_ROOT / "data" / "standards_corpus.json"

# One vocabulary for both source vocabularies. Keys are lowercased source
# values; values are the canonical snake_case sector.
CATEGORY_MAP = {
    # Source A (mock_corpus): Title Case with ampersands.
    "electrical cables & wires": "electrical_cables",
    "cement & building materials": "cement_building_materials",
    "steel pipes & fittings": "steel_pipes_fittings",
    # Source B (raw/standards.json): snake_case.
    "electrical_cables": "electrical_cables",
    "electrical_installations": "electrical_installations",
    "metal_pipes": "steel_pipes_fittings",
    "plastic_pipes": "plastic_pipes",
    "structural_steel": "structural_steel",
    "ppe": "ppe",
    # Source C (seed_standards): broader Title Case sector names.
    "civil construction & infrastructure": "structural_steel",
    "electrical & energy": "electrical_installations",
    "occupational health & safety": "ppe",
    "water supply & plumbing": "plastic_pipes",
}

# Supersessions that cross standard-number families, which the family-name
# heuristic in `retrieval/postprocess.py` cannot detect on its own. A
# withdrawn standard is usually replaced by one in the same family
# (IS 1554 (Part 1):1988 -> :2020), but occasionally by an entirely
# different number, as here.
#
# NOTE: unverified. These reflect the widely-documented replacements for
# these two withdrawn steel standards, but have not been confirmed against
# the BIS catalogue. Treat as placeholder like the rest of the corpus.
CROSS_FAMILY_SUPERSESSION = {
    "IS 226:1975": "IS 2062:2011",
    "IS 1139:1966": "IS 1786:2008",
}

# Sector prefixes for generated ids.
SECTOR_PREFIX = {
    "electrical_cables": "ELEC",
    "electrical_installations": "ELECINST",
    "cement_building_materials": "CEM",
    "steel_pipes_fittings": "STEEL",
    "plastic_pipes": "PIPE",
    "structural_steel": "STRUCT",
    "ppe": "PPE",
}


def normalize_is_number(number: str) -> str:
    """Normalize an IS number so the same standard compares equal.

    ``IS 1554 (part 1):1988`` and ``IS 1554 (Part 1):1988`` are one standard.
    """
    n = " ".join(number.strip().split())
    n = re.sub(r"\(\s*part\s*", "(Part ", n, flags=re.IGNORECASE)
    n = re.sub(r"\s*\)", ")", n)
    n = re.sub(r"\s*:\s*", ":", n)
    return n


def standard_family(number: str) -> str:
    """The part of an IS number before the edition year.

    ``IS 1554 (Part 1):1988`` -> ``IS 1554 (PART 1)``. Used to detect that a
    superseded standard has an active sibling.
    """
    return normalize_is_number(number).split(":")[0].upper()


def canonical_category(value: str) -> str:
    key = value.strip().lower()
    if key not in CATEGORY_MAP:
        raise KeyError(
            f"Unmapped category {value!r}. Add it to CATEGORY_MAP in this script "
            "so the merged corpus keeps a single vocabulary."
        )
    return CATEGORY_MAP[key]


def _richness(record: dict) -> int:
    """How much text the retrieval pipeline would get to embed."""
    return len(record.get("scope") or "") + len(record.get("description") or "")


def load_source_a() -> list:
    records = json.loads(SOURCE_A.read_text(encoding="utf-8"))
    for r in records:
        r["_source"] = "mock_corpus"
    return records


def load_source_b() -> list:
    records = json.loads(SOURCE_B.read_text(encoding="utf-8"))
    for r in records:
        r["_source"] = "raw_standards"
    return records


def load_source_c() -> list:
    """Source C uses a different schema; map it onto the common one."""
    payload = json.loads(SOURCE_C.read_text(encoding="utf-8"))
    mapped = []
    for s in payload.get("standards", []):
        mapped.append(
            {
                "id": None,
                "number": s["standard_number"],
                "title": s.get("title", ""),
                "scope": s.get("scope_text", ""),
                "description": s.get("abstract", ""),
                # Source C's sector values already match the snake_case style.
                "category": s.get("sector") or s.get("category_id") or "structural_steel",
                "version": str(s.get("current_version") or s.get("year_published") or ""),
                "last_amended": None,
                "status": s.get("status", "active"),
                "keywords": [],
                "_source": "seed_standards",
            }
        )
    return mapped


def merge(records: list) -> list:
    """Merge records keyed by normalized IS number, richest text winning."""
    by_number: dict = {}
    for r in records:
        key = normalize_is_number(r["number"])
        existing = by_number.get(key)
        if existing is None:
            by_number[key] = dict(r, sources=[r["_source"]])
            continue

        sources = existing["sources"] + [r["_source"]]
        if _richness(r) > _richness(existing):
            winner = dict(r)
        else:
            winner = dict(existing)
            # Keep any keywords the loser contributed.
            merged_keywords = list(
                dict.fromkeys((existing.get("keywords") or []) + (r.get("keywords") or []))
            )
            winner["keywords"] = merged_keywords
        winner["sources"] = sorted(set(sources))
        by_number[key] = winner

    merged = []
    for key, r in by_number.items():
        category = canonical_category(r["category"])
        merged.append(
            {
                "number": key,
                "title": r["title"],
                "scope": r.get("scope") or "",
                "description": r.get("description") or "",
                "category": category,
                "family": standard_family(key),
                "version": str(r.get("version") or ""),
                # Empty string rather than null: the `Standard` model in
                # standards-retrieval/data/models.py types this as a
                # required str, and not every source records an amendment.
                "last_amended": r.get("last_amended") or "",
                "status": (r.get("status") or "active").lower(),
                # Explicit replacement when it lives in a different family;
                # None means "same family, resolved by post-processing".
                "superseded_by_number": CROSS_FAMILY_SUPERSESSION.get(key),
                "keywords": r.get("keywords") or [],
                "sources": r["sources"],
                # Provenance: none of this is verified against the BIS
                # catalogue. Kept explicit so no downstream consumer can
                # mistake it for authoritative data.
                "verified": False,
            }
        )

    # Deterministic order, then assign ids per sector.
    merged.sort(key=lambda r: (r["category"], r["number"]))
    counters: Counter = Counter()
    for r in merged:
        prefix = SECTOR_PREFIX[r["category"]]
        counters[prefix] += 1
        r["id"] = f"IS-{prefix}-{counters[prefix]:03d}"

    return merged


def validate(corpus: list) -> list:
    """Return a list of human-readable problems; empty means valid."""
    problems = []

    ids = [r["id"] for r in corpus]
    numbers = [r["number"] for r in corpus]
    for label, values in (("id", ids), ("number", numbers)):
        dupes = [v for v, n in Counter(values).items() if n > 1]
        if dupes:
            problems.append(f"duplicate {label}s: {dupes}")

    for r in corpus:
        if not r["title"].strip():
            problems.append(f"{r['id']} ({r['number']}): empty title")
        if not r["scope"].strip():
            problems.append(f"{r['id']} ({r['number']}): empty scope")
        if r["status"] not in {"active", "superseded"}:
            problems.append(f"{r['id']} ({r['number']}): unexpected status {r['status']!r}")

    # A superseded standard is only meaningful if an active sibling exists;
    # the post-processing stage needs that pair to apply its penalty.
    families = {}
    for r in corpus:
        families.setdefault(r["family"], []).append(r)
    all_numbers = set(numbers)
    for family, members in families.items():
        statuses = {m["status"] for m in members}
        if "superseded" in statuses and "active" not in statuses:
            # Acceptable when every superseded member names a replacement
            # that exists in the corpus.
            unresolved = [
                m
                for m in members
                if m["status"] == "superseded"
                and m.get("superseded_by_number") not in all_numbers
            ]
            if unresolved:
                problems.append(
                    f"family {family}: superseded with no active sibling and no "
                    "resolvable superseded_by_number "
                    "(supersession penalty cannot resolve)"
                )

    # A declared replacement must actually exist.
    for r in corpus:
        target = r.get("superseded_by_number")
        if target and target not in all_numbers:
            problems.append(
                f"{r['id']} ({r['number']}): superseded_by_number {target!r} "
                "is not in the corpus"
            )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate only; do not write the merged corpus",
    )
    args = parser.parse_args()

    records = load_source_a() + load_source_b() + load_source_c()
    corpus = merge(records)
    problems = validate(corpus)

    print(f"sources          : {len(records)} records in")
    print(f"merged corpus    : {len(corpus)} unique standards")
    print(f"sectors          : {len(Counter(r['category'] for r in corpus))}")
    for sector, count in sorted(Counter(r["category"] for r in corpus).items()):
        print(f"  {sector:<28} {count:>3}")
    status_counts = Counter(r["status"] for r in corpus)
    print(f"status           : {dict(status_counts)}")
    multi = [r for r in corpus if len(r["sources"]) > 1]
    print(f"merged from >1 source: {len(multi)}")

    if problems:
        print(f"\nVALIDATION FAILED ({len(problems)} problems):")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("\nvalidation: OK")

    if args.check:
        print("(--check: nothing written)")
        return 0

    OUTPUT.write_text(
        json.dumps(corpus, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUTPUT.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
