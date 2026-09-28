"""Add the standards BIS lists as current that the archive never had.

The archive snapshot behind the corpus stops short of BIS's catalogue. Of
the standards BIS's own record lists as current, thousands are absent from
the corpus altogether, and thousands more are held only in an older edition.
Search cannot recommend a standard it does not hold, and "cite the latest
edition" means little when that edition cannot be opened.

Each such edition is added carrying what BIS's record gives: its number,
official title and status. There is no scope text, so, like the archive
records kept on number and title only, it is searchable on its title alone
and says so (provenance 'number_and_title_only', source BIS's Know Your
Standard page). Records already in the corpus are never touched, and new ids
use their own prefix (IS-BIS-nnnnn) so no existing id shifts.

Order in the pipeline:
  python data/build_full_corpus.py      (archive and curated records, ids)
  python data/add_bis_standards.py      (this: BIS's current standards not held)
  python data/apply_bis_status.py       (BIS's status, replacements and titles)

Usage:
  python data/add_bis_standards.py [--dry-run]
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_bis_status import _year, clean_bis_title, tidy_replacement  # noqa: E402
from build_full_corpus import KYS_URL, family, keywords_from, mark_superseded_editions, normalize  # noqa: E402
from ingest_archive import classify  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = _REPO_ROOT / "data" / "standards_corpus_full.json"
BIS = _REPO_ROOT / "data" / "amendments" / "bis_kys.json"
ID_PREFIX = "IS-BIS-"


def corpus_spelling(bis_number):
    """'IS 101 (PART 1/SEC 2):2023' -> 'IS 101 (Part 1/Sec 2):2023', or None if it is not a standard."""
    number, _ = tidy_replacement(bis_number)
    return normalize(number) if number else None


def additions(corpus, bis):
    """(records to add, counts) for BIS's current editions the corpus lacks."""
    held = {normalize(r["number"]).upper() for r in corpus}
    newest_held = {}
    for record in corpus:
        fam = family(record["number"])
        newest_held[fam] = max(newest_held.get(fam, 0), _year(record["number"]))
    next_id = 1 + max((int(r["id"][len(ID_PREFIX):]) for r in corpus if r["id"].startswith(ID_PREFIX)), default=0)

    added, counts = [], Counter()
    for raw in sorted(bis, key=lambda n: (_year(n), n)):
        entry = bis[raw]
        if entry.get("withdrawn"):
            continue
        number = corpus_spelling(raw)
        # A handful of BIS pages print the number oddly and it was read
        # truncated ("IS/IEC 60255-21-", "IS/IEC6004"); those are left out
        # rather than added under a number nobody can cite.
        if not number or not _year(number) or not re.match(r"^(?:IS|SP)(?:/[A-Z]+)*\s\d", number):
            counts["malformed number"] += 1
            continue
        if number.upper() in held:
            continue
        fam, year = family(number), _year(number)
        if fam in newest_held and year <= newest_held[fam]:
            counts["older than the edition held"] += 1
            continue
        title = clean_bis_title(entry.get("title"))
        if not title:
            counts["no title"] += 1
            continue
        kind = "newer edition of a standard held" if fam in newest_held else "standard not held at all"
        counts[kind] += 1
        added.append({
            "number": number,
            "title": title,
            "scope": "",
            "description": "",
            "category": classify(title, "") or "general",
            "family": fam,
            "version": str(year) if year else "",
            "last_amended": "",
            "status": "active",
            "superseded_by_number": None,
            "keywords": keywords_from(title, ""),
            "sources": ["bis.gov.in/knowyourstandards"],
            "source_url": KYS_URL.format(id=entry["page_id"]) if entry.get("page_id") else None,
            "verified": False,
            "provenance": "number_and_title_only",
            "status_source": "bis",
            "title_source": "bis",
            "id": f"{ID_PREFIX}{next_id:05d}",
        })
        next_id += 1
        held.add(number.upper())
        newest_held[fam] = max(newest_held.get(fam, 0), year)
    return added, counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    bis = json.loads(BIS.read_text(encoding="utf-8"))["standards"]
    added, counts = additions(corpus, bis)
    print(f"corpus {len(corpus)}; adding {len(added)}: {dict(counts)}")
    print("examples:", [(r["number"], r["title"][:50], r["category"]) for r in added[:6]])
    if args.dry_run:
        return 0
    corpus.extend(added)
    # The build's rule, applied again now that newer editions are held: an
    # older archive edition is superseded by the newest edition of the same
    # standard (IS 2167:2019 by IS 2167:2025), even where BIS still lists the
    # old one as live during a transition.
    marked = mark_superseded_editions(corpus)
    print(f"older archive editions marked superseded by a newer edition now held: {marked}")
    CORPUS.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {CORPUS} ({len(corpus)} records)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
