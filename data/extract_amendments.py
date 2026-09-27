"""Read published amendments from the standards' own text.

The archive copies of Indian Standards (the cached texts under
data/archive/cache/, one per corpus standard) often carry their amendment
slips bound in, each opening with a header like

    AMENDMENT NO. 1 AUGUST 1991
    TO
    IS 10 ( Part 4 ) : 1989 PLYWOOD TEA-CHESTS - SPECIFICATION

followed by the alterations ("( Page 1, clause 4.1, line 1 ) - Delete ...").
Reprints also say "incorporating Amendment No. 1 and 2". Both are read here.

Rules, because a wrong amendment count in a tender citation is worse than none:

* A slip counts only if its "TO IS ..." names the standard the text belongs
  to. Slips for other standards are ignored.
* Amendments are numbered in sequence, so the highest number found is the
  count in that copy. Numbers below it that were not read are listed as
  known-to-exist with no date, never with an invented one.
* A copy only holds the amendments issued before it was made. Each result
  records how recent the copy is (the latest amendment, reprint or
  reaffirmation date in it), and the engine says later amendments may exist.
* A standard whose text has no slip is recorded as "none in the archived
  copy", with the copy's date, which is not a statement that it has none.

Output: data/amendments/extracted_amendments.json

Usage:
  python data/extract_amendments.py [--sample N]
"""

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "data"))

from extract_references import CACHE, load_corpus  # noqa: E402

OUTPUT = _REPO_ROOT / "data" / "amendments" / "extracted_amendments.json"

_MONTHS = {m[:3]: i for i, m in enumerate(
    ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
     "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"], start=1)}
_MONTH = r"(JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUNE?|JULY?|AUG(?:UST)?|SEPT?(?:EMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)"
_YEAR = r"((?:19[4-9]|20[0-3])\d)"

# Case-sensitive: slip headers are set in capitals. A lower-case "(Amendment
# No. 1)" is a mention inside other text, not a slip.
_SLIP = re.compile(r"AMENDMENT\s*N[O0]\s*\.?\s*(\d{1,2})\b")
_DATE = re.compile(rf"\b{_MONTH}\.?\s*,?\s*{_YEAR}\b", re.IGNORECASE)
# The standard a slip amends, named right after its number and date:
#   "TO IS 10 ( Part 4 ) : 1989", "TO IS : 1- 1968", "TO IS:100OQ(Part 2)-1980",
#   "TO AUGUST 1989 IS : 6896 - 1973", "FOR IS : 3347 ( Part S/Set 2 )- 1979",
#   "TO rs 10111: 1982", "TO 18 1264:1997", and OCR-damaged numbers such as
#   "IS 11\"7: 1987" or "IS 1203': 1'8'". The edition year after the number is
#   required: it is what separates a slip header from a passing citation.
_HEADER = re.compile(
    r"(?:\bIS|\bI5|\b1S|\blS|\brs|\b18|\b15)\s*(?:[:.|;]|\bt\b)?\s*(?:I\s+)?"
    r"([0-9lIOoQ'\"*~?^!&]{1,7})(?:\s*-\s*\d{1,3}){0,2}\s*"      # dash parts: IS 302-2-206
    # The part, however OCR left it: "( Part 4 )", "( PART 2/SEC 5 )",
    # "( PART H )", "(P«rt D", "[P:118]".
    r"(?:\(\s*P\W?[aA]?r\s*t\s*([0-9IVXl]{1,5}\b)?[^)]{0,16}\)?|\[\s*P\s*:\s*\d{1,3}\s*\])?\s*"
    r"[:\-\[�>H.]{1,3}\s*([0-9'\"*^A-Z]{4})",               # damaged year: 198A, H971, 19^7",
    re.IGNORECASE,
)


_BARE_SLIP = re.compile(
    rf"\s*{_MONTH}\.?\s*,?\s*[0-9]{{4}}\s*(?:Alter|Addend|Corrig|\(\s*Pa[gq]e)",
    re.IGNORECASE,
)


def _fits(token: str, own_base: str, same_year: bool) -> bool:
    """Whether a number read from a slip header is the standard's own.

    An exact match always fits. Characters OCR could not read (' " * ~) match
    anything, and with the edition year confirming it one misread digit is
    allowed ("13125" for 13123). A clean, different number is another
    standard's slip.
    """
    token = token.translate(str.maketrans("lIOoQ", "11000"))
    if token.lstrip("0") == own_base:
        return True
    if token.startswith(("18", "15")) and token[2:] == own_base:
        return True                                  # "IS" read as 18 or 15
    if len(token) != len(own_base) or len(own_base) < 2:
        return False
    wrong_digit = sum(1 for t, o in zip(token, own_base) if t.isdigit() and t != o)
    agree = sum(1 for t, o in zip(token, own_base) if t == o)
    return agree >= len(own_base) - 1 and wrong_digit <= (1 if same_year else 0)


def _tidy_head(head: str) -> str:
    """Undo OCR spacing in a slip header: 'I S : 7 6 3 3 - 1 9 8 2' -> 'IS : 7633 - 1982'."""
    head = re.sub(r"\bI\s+S\b", "IS", head)
    head = re.sub(r"\bT\s+O\b", "TO", head)
    return re.sub(r"(?<=\d) (?=\d)", "", head)
# "Incorporating Amendments No. 1 to 9", "Incorporating Amendment No. 1 & 2".
# Whole one- or two-digit numbers only: "Incorporating Amendment No. 1982"
# is a damaged line, not amendment 19.
_INCORPORATING = re.compile(
    r"incorporating\s+amendments?\s+nos?\s*\.?\s*((?:\d{1,2}(?!\d)\s*(?:,|&|and|to|-)?\s*){1,10})(?!\d)",
    re.IGNORECASE,
)
_REPRINT = re.compile(rf"(?:Reprint|Reaffirmed)\D{{0,30}}?(?:{_MONTH}\.?\s*)?{_YEAR}", re.IGNORECASE)
_SLIP_END = re.compile(r"Reprograph|AMENDMENT\s*N[O0]|\bFOREWORD\b|Indian Standard\s+[A-Z]", re.IGNORECASE)
_ALTERATION = re.compile(r"\(\s*Pa[gq]e\s*\d", re.IGNORECASE)
_ROMAN = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6", "VII": "7", "VIII": "8", "IX": "9", "X": "10"}


def _digits(token: str) -> str:
    """OCR renders 1 as l or I and 0 as O, o or Q inside numbers."""
    return token.translate(str.maketrans("lIOoQ", "11000")).lstrip("0") or "0"


def _part(token):
    if not token:
        return None
    token = token.upper().replace("L", "I")
    return _ROMAN.get(token, token.lstrip("0"))


def _own(number: str):
    m = re.match(r"IS\s*(?:/\s*(?:IEC|ISO)\s*)?(\d+)(?:\s*\(Part\s*(\w+))?", number)
    return (m.group(1).lstrip("0") or "0", m.group(2)) if m else ("", None)


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:)])", r"\1", text)
    return text.replace("( ", "(").strip()


def read(number: str, edition_year: int, text: str):
    """Amendments bound into one standard's text, and how recent the copy is."""
    own_base, own_part = _own(number)
    found = {}
    dates_seen = []

    for m in _SLIP.finditer(text):
        n = int(m.group(1))
        if not 1 <= n <= 20:
            continue
        head = _tidy_head(" ".join(text[m.end(): m.end() + 260].split()))
        head = _tidy_head(" ".join(text[m.end(): m.end() + 260].split()))
        target = _HEADER.search(head)
        if not target or target.start() > 70:
            # Some slips are bound in with no "TO IS ..." line at all:
            # "AMENDMENT NO. 1 JULY 1977 Alterations (Page 4, clause 3.3 ...".
            # A dated header followed straight by alterations is this
            # standard's own slip; anything else is not a slip.
            if not _BARE_SLIP.match(head):
                continue
        else:
            year_digits = re.sub(r"\D", "", target.group(3))
            same_year = bool(len(year_digits) == 4 and edition_year and int(year_digits) == edition_year)
            if not _fits(target.group(1), own_base, same_year):
                continue                                 # a slip for another standard
            part = _part(target.group(2))
            if own_part and part and part != own_part and not same_year:
                continue
        date = None
        dm = _DATE.search(text[max(0, m.start() - 10): m.end() + 200])
        if dm:
            year = int(dm.group(2))
            if edition_year <= year <= 2030:
                date = f"{year}-{_MONTHS[dm.group(1)[:3].upper()]:02d}"
                dates_seen.append(year)
        # The body is read from the raw text after the header: tidying changed
        # offsets, so find where the alterations start from the slip onward.
        body = text[m.end(): m.end() + 1600]
        stop = _SLIP_END.search(body)
        body = body[: stop.start()] if stop else body
        alt = _ALTERATION.search(body)
        excerpt = _clean(body[alt.start():])[:260] if alt else None
        current = found.get(n)
        if current is None or (current["date"] is None and date) or (not current["excerpt"] and excerpt):
            found[n] = {"number": n, "date": date, "excerpt": excerpt, "source": "slip"}

    # A reprint repeats its "incorporating" line on several pages, and OCR
    # sometimes damages one copy ("No. 1)" read as "No. 11"). When the copies
    # disagree, the reading that occurs most often wins.
    readings = Counter()
    # OCR renders "&" as "8t", "8c" or "&t": "No. 1 8t 2" is "No. 1 & 2".
    text_inc = re.sub(r"(?<=\d)\s+(?:8t|8c|&t|&c)\s+(?=\d)", " & ", text)
    for m in _INCORPORATING.finditer(text_inc):
        nums = [int(x) for x in re.findall(r"\d{1,2}", m.group(1))]
        if re.search(r"\bto\b|-", m.group(1)) and len(nums) == 2 and nums[0] < nums[1]:
            nums = list(range(nums[0], nums[1] + 1))
        # A list of amendments climbs a step at a time; a number far past the
        # one before it is a misread character, not amendment 8 after 1.
        kept = []
        for n in sorted(set(nums)):
            if 1 <= n <= 20 and (not kept or n <= kept[-1] + 2):
                kept.append(n)
        nums = tuple(kept)
        if nums:
            readings[nums] += 1
    incorporated = set(readings.most_common(1)[0][0]) if readings else set()

    for m in _REPRINT.finditer(text):
        year = int(m.group(2))
        if edition_year <= year <= 2030:
            dates_seen.append(year)

    highest = max([*found, *incorporated], default=0)
    amendments = []
    for n in range(1, highest + 1):
        if n in found:
            amendments.append(found[n])
        else:
            amendments.append({"number": n, "date": None, "excerpt": None,
                               "source": "incorporated" if n in incorporated else "implied"})
    return {
        "count_in_copy": highest,
        "amendments": amendments,
        "copy_as_of": max(dates_seen + [edition_year]) if edition_year else (max(dates_seen) if dates_seen else None),
    }


def build(sample=None):
    corpus, _, identifier = load_corpus()
    sources = corpus if sample is None else random.Random(11).sample(corpus, sample)
    standards, stats = {}, Counter()
    for record in sources:
        ident = identifier.get(record["number"])
        path = CACHE / f"{ident}.txt" if ident else None
        if not path or not path.exists():
            stats["no_text"] += 1
            continue
        m = re.search(r":(\d{4})$", record["number"])
        edition_year = int(m.group(1)) if m else 0
        result = read(record["number"], edition_year, path.read_text(encoding="utf-8", errors="replace"))
        standards[record["number"]] = result
        stats["read"] += 1
        if result["count_in_copy"]:
            stats["with_amendments"] += 1
            stats["amendments"] += result["count_in_copy"]
            stats["dated"] += sum(1 for a in result["amendments"] if a["date"])
    return standards, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, help="read a random sample, print, write nothing")
    args = ap.parse_args()
    started = time.time()
    standards, stats = build(args.sample)
    print(dict(stats), f"{time.time() - started:.0f}s")
    if args.sample:
        shown = [(n, r) for n, r in standards.items() if r["count_in_copy"]][:12]
        for n, r in shown:
            print(n, "| copy as of", r["copy_as_of"], "|",
                  [(a["number"], a["date"], a["source"], (a["excerpt"] or "")[:70]) for a in r["amendments"]])
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "_meta": {
            "method": (
                "Amendment slips and 'incorporating Amendment No.' notes read from the archived text "
                "of each standard (data/extract_amendments.py). A slip counts only when it names the "
                "standard it is bound into. Numbers below the highest found that were not read are "
                "listed without a date."
            ),
            "limit": (
                "A copy holds only amendments issued before it was made; copy_as_of is the latest "
                "amendment, reprint or reaffirmation year in it. Later amendments may exist."
            ),
            "standards_read": stats["read"],
            "with_amendments": stats["with_amendments"],
            "amendments": stats["amendments"],
        },
        "standards": standards,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
