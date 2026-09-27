"""Bring each edition's status up to date from BIS's own record.

The corpus marks an edition superseded only when it happens to hold a newer
edition of the same standard (build_full_corpus.mark_superseded_editions), so
an edition BIS withdrew years ago still reads as current when the corpus has
nothing newer. BIS's "Know Your Standard" page for each edition says whether
it is withdrawn and what replaced it (data/bis_kys.py, data/amendments/bis_kys.json).

For every corpus edition with a BIS record:

* withdrawn with a replacement -> status 'superseded', superseded_by_number
  set to BIS's replacement (which may be an edition the corpus does not hold)
* withdrawn with no replacement -> status 'superseded', withdrawn true,
  no replacement named
* not withdrawn -> left as the corpus has it: an edition superseded by a
  newer one the corpus holds stays superseded, since BIS sometimes keeps an
  old edition live during a transition

Every change records status_source 'bis'. Editions with no BIS record are
untouched. Only the full corpus is changed; the small test corpora keep
their own researched status.

Usage:
  python data/apply_bis_status.py [--dry-run]
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    bis = {normalize(k): v for k, v in json.loads(BIS.read_text(encoding="utf-8"))["standards"].items()}
    held = {normalize(r["number"]) for r in corpus}

    stats = Counter()
    examples = []
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
    if not args.dry_run:
        CORPUS.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {CORPUS}")


if __name__ == "__main__":
    main()
