"""Build the allied-standards graph from the text of the standards themselves.

The curated graph (relationships/relationships.json) holds 25 hand-read links
across 16 standards. Every standard in the archive carries its own list of
the standards it depends on, in a REFERENCES clause or a referred-standards
annex, so the cluster the problem statement asks for can be read rather than
researched one standard at a time.

What counts as a link, deliberately narrow:

* A standard cited in the source's REFERENCES clause or referred-standards
  annex. Inside that table the numbers usually appear without the "IS"
  prefix ("8130 : 1984 Conductors for insulated..."), so a number with an
  edition year is accepted there.
* A standard cited in the body with an explicit "IS" prefix ("see IS 10418",
  "conforming to IS 5831").

What is excluded:

* The standard citing itself (any edition of its own family).
* Sentences about history rather than dependency: "supersedes", "revision
  of", "first published", "withdrawn", "replaces".
* Anything whose number cannot be read cleanly.

Each link records the passage it was read from, so any edge can be checked by
a person. Citations are resolved to the corpus: an exact edition when held,
otherwise the current edition of the same standard, with the edition cited
recorded; a standard the corpus does not hold is kept and flagged
outside_corpus rather than dropped.

Run with::

    python data/extract_references.py --sample 300   # report only
    python data/extract_references.py                # write the graph
"""

import argparse
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "data"))

from ingest_archive import clean_ocr  # noqa: E402

CORPUS = _REPO_ROOT / "data" / "standards_corpus_full.json"
INGESTED = _REPO_ROOT / "data" / "archive" / "ingested_standards.json"
CACHE = _REPO_ROOT / "data" / "archive" / "cache"
MISFILED = _REPO_ROOT / "data" / "archive" / "misfiled.json"
OUTPUT = _REPO_ROOT / "data" / "relationships" / "extracted_relationships.json"

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8,
          "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15}

_YEAR = r"(19[2-9]\d|20[0-3]\d)"
_PART = r"(?:\s*\(\s*Part\s*([0-9]{1,3}|[IVX]{1,5})\s*(?:[/,]\s*Sec(?:tion)?\s*([0-9]{1,3}|[IVX]{1,5}))?\s*\))?"

# Inside a references block: a bare number with an edition year.
_BLOCK_CITE = re.compile(
    rf"(?<![\d./:])(?<!: )(?<!:  )(?:IS\s*[:.]?\s*)?(\d{{2,5}})(?![\dA-Za-z%])(?!\s*['`’]\s*\d){_PART}\s*[:\-–]\s*{_YEAR}(?!\d)",
    re.IGNORECASE,
)
# In the body: an explicit IS prefix, year optional.
_BODY_CITE = re.compile(
    # Not followed by a digit or a decimal part, but a sentence-ending full stop is
    # fine: "Grade A of IS 2062." is a citation.
    rf"\bIS\s*[:.]?\s*(\d{{2,5}})(?![\dA-Za-z%])(?!\s*['`’]\s*\d){_PART}(?:\s*[:\-–]\s*{_YEAR})?(?!\d|\.\d)",
)

_REF_HEADING = re.compile(
    r"(NORMATIVE\s+REFERENCES|\bREFERENCES\b|LIST\s+OF\s+REFERRED|REFERRED\s+(?:INDIAN\s+)?STANDARDS"
    r"|INDIAN\s+STANDARDS\s+REFERRED|following\s+Indian\s+Standards?\s+(?:are|is)\s+(?:necessary|referred))",
    re.IGNORECASE,
)
# Where a references block ends: the next numbered clause heading.
_NEXT_CLAUSE = re.compile(r"\s\d{1,2}\s+(?:TERMINOLOGY|DEFINITIONS?|GENERAL|REQUIREMENTS?|MATERIALS?|"
                          r"SYMBOLS|CLASSIFICATION|TYPES|GRADES?|DESIGNATION|SAMPLING|TESTS?|MARKING|PACKING)\b")
# Phrasings that mean history. Not a bare "replac": "part replacement of cement"
# is a material being substituted, not a standard being superseded.
_HISTORY = re.compile(r"supersed|revision of|first published|withdrawn|replaces\b|replaced by|amalgamat|in lieu of|earlier edition|under (?:revision|preparation|print)|previously (?:covered|published|specified)|formerly",
                      re.IGNORECASE)

_TYPE_RULES = [
    ("test_method", re.compile(r"method(s)? of (test|sampling|analysis|measurement)|test method|testing of|sampling", re.I)),
    ("terminology", re.compile(r"glossary|vocabulary|terminology|definitions|symbols", re.I)),
    ("installation", re.compile(r"code of practice|installation|laying|erection", re.I)),
]


def _arabic(token):
    if not token:
        return None
    token = token.upper()
    return str(_ROMAN[token]) if token in _ROMAN else token.lstrip("0") or "0"


# No Indian Standard is numbered this high; larger values are OCR noise.
_MAX_IS_NUMBER = 19999

# The publication imprint ("(c) BIS 2009  BUREAU OF INDIAN STANDARDS") OCRs as
# "IS 2009". A citation immediately followed by the imprint is not a citation.
_IMPRINT = re.compile(r"B\s*U\s*R\s*E\s*A\s*U\s+O\s*F", re.IGNORECASE)

# In a references table a bare number is accepted, so one belonging to another
# body ("ISO 9001 : 2000", "IEC 60227") must not be read as an Indian Standard.
# "1S0", "IS0", "LSO" and "I5O" are how OCR often renders "ISO" ("LSO 53:1998"
# had become a citation of IS 53, Brunswick green, in a gear standard).
_FOREIGN_BODY = re.compile(r"(?:ISO|IS0|1S0|LSO|I5O|lSO|I\s?SO|IEC|EN|BS|DIN|ASTM|ANSI|JIS)\s*[:/-]?\s*$",
                           re.IGNORECASE)


def _family(base, part, sec=None):
    fam = f"IS {int(base)}"
    if part:
        fam += f" (PART {part}"
        fam += f"/SEC {sec})" if sec else ")"
    return fam


def load_corpus():
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    by_family = defaultdict(list)
    for r in corpus:
        by_family[r["family"].upper()].append(r)
    ingested = json.loads(INGESTED.read_text(encoding="utf-8"))["standards"]
    identifier = {s["number"]: s["identifier"] for s in ingested if s.get("identifier")}
    return corpus, by_family, identifier


def _year_of(number):
    m = re.search(r":(\d{4})$", number)
    return int(m.group(1)) if m else 0


def resolve(fam, year, by_family):
    """Pick the corpus record a citation points at, or None if not held."""
    editions = by_family.get(fam)
    if not editions:
        return None, None
    if year:
        for r in editions:
            if _year_of(r["number"]) == int(year):
                return r, "exact"
    current = [r for r in editions if r.get("status") == "active"] or editions
    return max(current, key=lambda r: _year_of(r["number"])), "current"


def _classify(title):
    for kind, pattern in _TYPE_RULES:
        if pattern.search(title or ""):
            return kind
    return "normative_reference"


def _snippet(text, start, end):
    a, b = max(0, start - 60), min(len(text), end + 60)
    return " ".join(text[a:b].split())


def _references_block(text):
    """The REFERENCES clause or referred-standards annex, if the text has one."""
    for m in _REF_HEADING.finditer(text):
        tail = text[m.end(): m.end() + 5000]
        stop = _NEXT_CLAUSE.search(tail, 200)
        block = tail[: stop.start()] if stop else tail[:3000]
        if _BLOCK_CITE.search(block):
            return m.end(), block
    return None, ""


def extract(source, text, by_family):
    """Citations in one standard's text, as (family, year, evidence, where)."""
    own = source["family"].upper()
    # The source's own number cited without a part is almost always its own page
    # header with the part garbled by OCR, not a citation of the whole family.
    own_base = re.match(r"IS (\d+)", own)
    own_base = own_base.group(1) if own_base else None
    found = {}

    def is_self(base, part, text=None, end=None):
        if fam_of(base, part) == own or (not part and base.lstrip("0") == own_base):
            return True
        # Its own number with the next clause number run into it: "IS : 1811
        # 3. SAMPLING" read as IS 18113, "IS:13141. SCOPE" in IS 1314.
        digits = base.lstrip("0")
        return bool(own_base and text is not None and digits.startswith(own_base)
                    and 0 < len(digits) - len(own_base) <= 2
                    and re.match(r"\s*\.\s*[A-Z]{3,}", text[end:end + 20]))

    def fam_of(base, part):
        return _family(base, part)

    start, block = _references_block(text)
    if block:
        for m in _BLOCK_CITE.finditer(block):
            if int(m.group(1)) > _MAX_IS_NUMBER or _FOREIGN_BODY.search(block[max(0, m.start() - 8): m.start()]):
                continue
            fam = _family(m.group(1), _arabic(m.group(2)), _arabic(m.group(3)))
            if not is_self(m.group(1), _arabic(m.group(2))):
                found.setdefault(fam, (m.group(4), _snippet(block, m.start(), m.end()), "references"))

    for m in _BODY_CITE.finditer(text):
        if int(m.group(1)) > _MAX_IS_NUMBER or _IMPRINT.search(text, m.end(), m.end() + 40):
            continue
        fam = _family(m.group(1), _arabic(m.group(2)), _arabic(m.group(3)))
        if is_self(m.group(1), _arabic(m.group(2)), text, m.end()) or fam in found:
            continue
        # The clause around the citation, for the history filter. Bounded both by
        # sentence ends and by distance: lists of materials run for hundreds of
        # characters without a full stop, and a "supersedes" far along such a list
        # says nothing about this citation.
        left = max(text.rfind(".", 0, m.start()) + 1, m.start() - 120)
        right = min(text.find(".", m.end()) % (len(text) + 1) or len(text), m.end() + 120)
        if _HISTORY.search(text[left:right]):
            continue
        found[fam] = (m.group(4), _snippet(text, m.start(), m.end()), "body")

    return found


def build(sample=None):
    corpus, by_family, identifier = load_corpus()
    sources = corpus if sample is None else random.Random(7).sample(corpus, sample)

    relationships, no_text, with_refs = [], 0, 0
    wrong_text = set(json.loads(MISFILED.read_text(encoding="utf-8"))["misfiled"]) if MISFILED.exists() else set()
    read_without_citations = []
    kinds, where_counts, resolution = Counter(), Counter(), Counter()
    for source in sources:
        ident = identifier.get(source["number"])
        path = CACHE / f"{ident}.txt" if ident and ident not in wrong_text else None
        if not path or not path.exists():
            no_text += 1
            continue
        text = clean_ocr(path.read_text(encoding="utf-8", errors="replace"))
        found = extract(source, text, by_family)
        if found:
            with_refs += 1
        else:
            read_without_citations.append(source["number"])
        for fam, (year, evidence, where) in found.items():
            # A cited part the corpus does not hold stays outside the corpus: the
            # whole-standard family would be a different document, not a match.
            target, how = resolve(fam, year, by_family)
            cited = fam.title().replace("Is ", "IS ").replace("(Part", "(Part").replace("/Sec", "/Sec")
            cited = cited + (f":{year}" if year else "")
            # Compact on purpose (88k links): titles are looked up from the corpus
            # when served, and the method is recorded once in _meta.
            rel = {
                "source": source["number"],
                "target": target["number"] if target else cited,
                "type": _classify(target["title"] if target else ""),
                "cited_as": cited,
                "resolution": how or "outside_corpus",
                "outside_corpus": target is None,
                "found_in": where,
                "evidence": evidence[:160],
            }
            if target is not None and how != "exact" and year:
                rel["note"] = f"Cited as {cited}; the corpus holds {target['number']}."
            relationships.append(rel)
            kinds[rel["type"]] += 1
            where_counts[where] += 1
            resolution[rel["resolution"]] += 1

    return {
        "sources": len(sources), "no_text": no_text, "with_refs": with_refs,
        "relationships": relationships, "read_without_citations": read_without_citations, "kinds": kinds, "where": where_counts, "resolution": resolution,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, help="process a random sample and report; write nothing")
    args = parser.parse_args()

    started = time.time()
    result = build(args.sample)
    rels = result["relationships"]
    print(f"standards read     : {result['sources'] - result['no_text']} (no cached text: {result['no_text']})")
    print(f"  citing others    : {result['with_refs']}")
    print(f"links found        : {len(rels)}")
    print(f"  found in         : {dict(result['where'])}")
    print(f"  resolved         : {dict(result['resolution'])}")
    print(f"  types            : {dict(result['kinds'])}")
    print(f"took {time.time() - started:.0f}s")

    if args.sample:
        for r in random.Random(3).sample(rels, min(12, len(rels))):
            print(f"\n  {r['source']} -> {r['target']}  [{r['resolution']}, {r['found_in']}]")
            print(f"     \"{r['evidence'][:160]}\"")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "_meta": {
            "purpose": "Allied-standards graph read from the text of the standards themselves.",
            "generated": time.strftime("%Y-%m-%d"),
            "method": (
                "Citations in each standard's REFERENCES clause or referred-standards annex (a number with an "
                "edition year), plus explicit 'IS' citations in the body. Self-citations and sentences about "
                "history (supersedes, revision of, withdrawn) are excluded. Source text is OCR of scanned "
                "documents, so a small share of links may be misread; each carries the passage it came from."
            ),
            "sources_read": result["sources"] - result["no_text"],
            "count": len(rels),
            "relation_method": "extracted",
        },
        # Read, and found to cite no other standard: distinct from "not read".
        "read_without_citations": sorted(result["read_without_citations"]),
        "relationships": rels,
    }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
