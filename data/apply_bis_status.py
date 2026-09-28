"""Bring each edition's status up to date from BIS's own record.

The corpus marks an edition superseded only when it happens to hold a newer
edition of the same standard (build_full_corpus.mark_superseded_editions), so
an edition BIS withdrew years ago still reads as current when the corpus has
nothing newer. BIS's "Know Your Standard" page for each edition says whether
it is withdrawn and what replaced it (data/bis_kys.py, data/amendments/bis_kys.json).

For every corpus edition with a BIS record:

* withdrawn with a replacement -> status 'superseded', superseded_by_number
  set to BIS's replacement (which may be an edition the corpus does not hold)
* withdrawn, no replacement named, but BIS lists a newer edition of the same
  standard as current -> that edition, with replacement_source
  'bis_newer_edition' (BIS's record for IS 4246:2002 names nothing, yet BIS
  lists IS 4246:2025 as in force)
* withdrawn, no replacement named, no current edition, but a newer edition
  was itself withdrawn and replaced -> that replacement, also
  'bis_newer_edition' (IS 12269:1987 names nothing; IS 12269:2013 went into
  IS 269:2015, which is in force)
* withdrawn with no replacement and no newer edition -> status 'superseded',
  withdrawn true, no replacement named
* not withdrawn -> left as the corpus has it: an edition superseded by a
  newer one the corpus holds stays superseded, since BIS sometimes keeps an
  old edition live during a transition

Every change records status_source 'bis'. Editions with no BIS record are
untouched. Only the full corpus is changed; the small test corpora keep
their own researched status.

Titles: an archive title can be broken in three ways, the archive's item id
in place of a title ("gov.in.is.16242.1.2014"), the edition year glued to the
front ("2019: Laying of Paver Blocks"), or a lower-case start from a mangled
catalogue entry. Such a title is replaced with BIS's official title for the
edition, minus the notes BIS appends ("(Withdrawn)", "(First Revision)"). An
all-capitals BIS title is used only when nothing better exists; otherwise the
archive title is mended (prefix removed, first letter capitalised). An id
with no BIS record for its edition takes BIS's title for another edition of
the same standard. The original is kept as archive_title, and title_source
says where the new one came from.

Usage:
  python data/apply_bis_status.py [--dry-run]
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from text_repair import fix_text  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = _REPO_ROOT / "data" / "standards_corpus_full.json"
BIS = _REPO_ROOT / "data" / "amendments" / "bis_kys.json"


def normalize(number: str) -> str:
    text = " ".join((number or "").strip().split())
    text = re.sub(r"\(\s*part\s*", "(Part ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\)", ")", text)
    text = re.sub(r"\s*:\s*", ":", text)
    return text.upper()


# What BIS writes in the "superseded by" field when nothing replaced the
# edition: a reason for the withdrawal, not a standard.
_NOT_A_STANDARD = re.compile(r"^(none|nil|na|n/a|null|-|standard withdrawn|withdrawn|decided by)", re.IGNORECASE)


def tidy_replacement(raw):
    """(replacement IS number or None, withdrawal note or None).

    BIS writes replacements loosely: 'IS 3400 (PART 5) : 2022/ISO 36 : 2020',
    'IS/ISO 603_1,IS/ISO 603_2', '101 (Part 1/SEC 4):2024' (no prefix), and
    puts reasons ('Decided by council') in the same field.
    """
    raw = " ".join((raw or "").split())
    if not raw or _NOT_A_STANDARD.match(raw):
        return None, (raw if raw and raw.lower() not in ("none", "na", "null", "nil", "-") else None)
    first = re.split(r"\s*,\s*", raw)[0]
    if not first.startswith(("IS/ISO", "IS/IEC")):
        first = re.split(r"/(?=ISO|IEC)", first)[0]
    first = first.replace("_", "-")
    if re.match(r"^\d", first):
        first = "IS " + first
    if not re.match(r"^(IS|SP)\b", first):
        return None, raw
    first = re.sub(r"\(\s*PART\s*", "(Part ", first, flags=re.IGNORECASE)
    first = re.sub(r"/\s*SEC(?:TION)?\s*", "/Sec ", first, flags=re.IGNORECASE)
    first = re.sub(r"\s*:\s*", ":", first).strip()
    return first, None


# --- titles -------------------------------------------------------------------

_ARCHIVE_ID = re.compile(r"^gov\.in\.", re.IGNORECASE)
_YEAR_PREFIX = re.compile(r"^(?:Part\s*\d+\s*(?::\s*Sec\s*\d+\s*)?:\s*)?(?:19|20)\d{2}\s*:\s*")
# Notes BIS appends to a title that are not part of it.
_BIS_NOTE = re.compile(
    r"\s*\(\s*(?:withdrawn|superseded|tentative|revised|modified|bi-?lingual|[^()]*\brevision\b[^()]*)\s*\)",
    re.IGNORECASE,
)


def clean_bis_title(raw):
    title = " ".join(_BIS_NOTE.sub("", fix_text(raw) or "").split()).strip(" .,-")
    return title[:1].upper() + title[1:]      # BIS's own record is sometimes lower-case too


def title_damage(title):
    """How a title is broken ('archive_id', 'year_prefix', 'lower_case'), or None."""
    text = (title or "").strip()
    if not text or _ARCHIVE_ID.match(text):
        return "archive_id"
    if _YEAR_PREFIX.match(text):
        return "year_prefix"
    if text[:1].islower():
        return "lower_case"
    return None


def repair_title(title, bis_title, other_edition_title):
    """(new title, where it came from) for a broken title, or (None, None) to leave it."""
    damage = title_damage(title)
    if damage is None:
        return None, None
    if damage == "archive_id":
        if bis_title:
            return bis_title, "bis"
        if other_edition_title:
            return other_edition_title, "bis_other_edition"
        return None, None
    if bis_title and not bis_title.isupper():
        return bis_title, "bis"
    mended = _YEAR_PREFIX.sub("", title.strip()) if damage == "year_prefix" else title.strip()
    mended = mended[:1].upper() + mended[1:]
    if mended and title_damage(mended) is None:
        return mended, "archive_mended"
    return (bis_title, "bis") if bis_title else (None, None)


def _stem(number):
    """Standard without its edition, spacing ignored: 'IS 101 (PART 1/SEC 2)' for any year."""
    return re.sub(r"\s+", "", re.sub(r":\s*\d{4}.*$", "", normalize(number)))


def _year(number):
    m = re.search(r":\s*(\d{4})", number or "")
    return int(m.group(1)) if m else 0


def current_editions(bis_raw):
    """The newest edition BIS lists as current, for each standard."""
    current = {}
    for number, entry in bis_raw.items():
        if not entry.get("withdrawn") and _year(number) > _year(current.get(_stem(number), "")):
            current[_stem(number)] = number
    return current


def newer_current_edition(number, current):
    """The edition BIS lists as current for this standard, if newer than this one."""
    newer = current.get(_stem(number))
    return tidy_replacement(newer)[0] if newer and _year(newer) > _year(number) else None


def later_edition_replacements(bis_raw):
    """For each standard, the newest edition's replacement, where BIS names one.

    BIS's record for IS 12269:1987 names no replacement, but the edition after
    it, IS 12269:2013, was merged into IS 269:2015: that is where the 1987
    edition's buyers went too.
    """
    newest = {}
    for number in bis_raw:
        if _year(number) > _year(newest.get(_stem(number), "")):
            newest[_stem(number)] = number
    out = {}
    for stem, number in newest.items():
        entry = bis_raw[number]
        replacement = tidy_replacement(entry.get("superseded_by"))[0] if entry.get("withdrawn") else None
        if replacement:
            out[stem] = (number, replacement)
    return out


def later_edition_replacement(number, later):
    """The replacement BIS names for a newer edition of this standard, if any."""
    found = later.get(_stem(number))
    return found[1] if found and _year(found[0]) > _year(number) else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    bis_raw = json.loads(BIS.read_text(encoding="utf-8"))["standards"]
    bis = {normalize(k): v for k, v in bis_raw.items()}
    held = {normalize(r["number"]) for r in corpus}

    # BIS's title for each standard, newest edition first, for an archive id
    # whose own edition BIS has no record of.
    title_by_stem = {}
    for number in sorted(bis_raw, key=_year, reverse=True):
        title = clean_bis_title(bis_raw[number].get("title"))
        if title:
            title_by_stem.setdefault(_stem(number), title)

    titles = Counter()
    title_examples = []
    for record in corpus:
        entry = bis.get(normalize(record["number"]))
        new, source = repair_title(record["title"], clean_bis_title(entry.get("title")) if entry else "",
                                   title_by_stem.get(_stem(record["number"])))
        damage = title_damage(record["title"])
        if damage:
            titles[f"{damage} -> {source or 'left'}"] += 1
        # Double-encoded text ("â€“" for an en dash), in the archive's title or
        # in one copied from BIS before its records were repaired.
        if new is None and fix_text(record["title"]) != record["title"]:
            new, source = fix_text(record["title"]), record.get("title_source") or "archive_mended"
            titles["garbled -> mended"] += 1
        elif new:
            new = fix_text(new)     # a mended title can still carry the garbling, so one run is enough
        if new and new != record["title"]:
            record.setdefault("archive_title", record["title"])
            record["title"] = new
            record["title_source"] = source
            if len(title_examples) < 8:
                title_examples.append((record["number"], record["archive_title"][:40], new[:60]))
    print("titles:", dict(titles))
    print("title examples:", title_examples)

    current_by_stem = current_editions(bis_raw)
    later_by_stem = later_edition_replacements(bis_raw)

    stats = Counter()
    examples = []
    newer_examples = []
    for record in corpus:
        entry = bis.get(normalize(record["number"]))
        if entry is None:
            stats["no_bis_record"] += 1
            continue
        stats["bis_record"] += 1
        if not entry.get("withdrawn"):
            stats["current_per_bis"] += 1
            continue
        replacement, note = tidy_replacement(entry.get("superseded_by"))
        record.pop("replacement_source", None)
        if not replacement:
            replacement = newer_current_edition(record["number"], current_by_stem)
            if not replacement:
                replacement = later_edition_replacement(record["number"], later_by_stem)
                if replacement:
                    stats["replaced_via_later_edition"] += 1
            if replacement:
                record["replacement_source"] = "bis_newer_edition"
                stats["replaced_by_newer_bis_edition"] += 1
                if len(newer_examples) < 8:
                    newer_examples.append((record["number"], replacement))
        was = record.get("status")
        record["status"] = "superseded"
        record["withdrawn"] = True
        record["status_source"] = "bis"
        if note:
            record["withdrawal_note"] = note
        if replacement:
            record["superseded_by_number"] = replacement
            stats["withdrawn_replaced_held" if normalize(replacement) in held else "withdrawn_replaced_not_held"] += 1
        else:
            record["superseded_by_number"] = None
            stats["withdrawn_no_replacement"] += 1
        if was == "active":
            stats["newly_marked"] += 1
            if len(examples) < 12:
                examples.append((record["number"], replacement))

    print(dict(stats))
    print("examples newly marked:", examples)
    print("examples named from BIS's newer edition:", newer_examples)
    if not args.dry_run:
        CORPUS.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {CORPUS}")


if __name__ == "__main__":
    main()
