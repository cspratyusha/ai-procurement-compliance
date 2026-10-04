"""Add the standards BIS lists as current that the archive never had.

The archive snapshot behind the corpus stops short of BIS's catalogue. Of
the standards BIS's own record lists as current, thousands are absent from
the corpus altogether, and thousands more are held only in an older edition.
Search cannot recommend a standard it does not hold, and "cite the latest
edition" means little when that edition cannot be opened.

Standards BIS published after its Know Your Standard snapshot (1 October
2025) come from its new portal (data/bis_portal.py, overlaid on the same
record) and are added the same way, sourced to standards.bis.gov.in.

Each such edition is added carrying what BIS's record gives: its number,
official title and status. There is no scope text, so, like the archive
records kept on number and title only, it is searchable on its title alone
and says so (provenance 'number_and_title_only', source BIS's Know Your
Standard page). Records already in the corpus are never touched, and new ids
use their own prefix (IS-BIS-nnnnn) so no existing id shifts.

Order in the pipeline:
  python data/build_full_corpus.py      (archive and curated records, ids)
  python data/bis_portal.py ...          (BIS's new portal, read before this step)
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
from bis_portal import overlay  # noqa: E402
from build_full_corpus import (  # noqa: E402
    KYS_URL, family, keywords_from, mark_superseded_editions, normalize, remap_query_sets,
)
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
    # The newest edition of each standard whose scope clause is held. A
    # revision rarely changes what a standard covers, and a new edition held on
    # its title alone otherwise loses, in search, to the edition it replaces
    # and to neighbours that have their text: IS 1299:2026 fell below IS 1313
    # for the very wording of IS 1299's own title.
    scoped_edition = {}
    for record in corpus:
        if record.get("scope") and record.get("provenance") == "published_text_ocr":
            fam = family(record["number"])
            if fam not in scoped_edition or _year(record["number"]) >= _year(scoped_edition[fam]["number"]):
                scoped_edition[fam] = record

    added, counts = [], Counter()
    for raw in sorted(bis, key=lambda n: (_year(n), n)):
        entry = bis[raw]
        # Withdrawn per the Know Your Standard snapshot: never added. Withdrawn
        # since (the portal's overlay): still added, and apply_bis_status marks
        # it superseded, so a later withdrawal neither hides an edition people
        # may have cited nor shifts the ids of the records after it.
        if entry.get("withdrawn") and entry.get("status_from") != "bis_portal":
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
        from_portal = entry.get("status_from") == "bis_portal" and not entry.get("page_id")
        if from_portal:
            counts["published after the Know Your Standard snapshot"] += 1
        earlier = scoped_edition.get(fam)
        inherited = earlier["scope"] if earlier and _year(earlier["number"]) < year else ""
        if inherited:
            counts["searched with the previous edition's scope"] += 1
        added.append({
            "number": number,
            "title": title,
            "scope": inherited,
            "description": "",
            "category": classify(title, inherited) or "general",
            "family": fam,
            "version": str(year) if year else "",
            "last_amended": "",
            "status": "active",
            "superseded_by_number": None,
            "keywords": keywords_from(title, inherited),
            "sources": ["standards.bis.gov.in" if from_portal else "bis.gov.in/knowyourstandards"],
            "source_url": entry.get("source_url") or (KYS_URL.format(id=entry["page_id"]) if entry.get("page_id") else None),
            **({"published_on": entry["published_on"]} if entry.get("published_on") else {}),
            "verified": False,
            "provenance": "scope_from_previous_edition" if inherited else "number_and_title_only",
            **({"scope_edition": earlier["number"]} if inherited else {}),
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
    # BIS's new portal: standards published, withdrawn or amended since the
    # Know Your Standard snapshot (data/bis_portal.py), when it has been read.
    print("BIS portal overlay:", overlay(bis))
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
    # Ids of BIS's records are assigned here, after the merge re-pointed the
    # query sets; re-point them again, or a label naming one of these
    # standards keeps the id another standard now has.
    remap_query_sets(corpus)
    return 0


if __name__ == "__main__":
    sys.exit(main())
