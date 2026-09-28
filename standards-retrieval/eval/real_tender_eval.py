"""How well the engine recovers the standards that real tender lines cite.

A tender line that reads "Providing and supplying HDPE pipes ... conforming to
IS 4984" is its own answer key: take the citation out, ask the engine, and see
whether it names IS 4984. Unlike the held-out set, whose queries were written
from the standards' own titles, this is buyers' language, with its
abbreviations, sizes, quantities and trade phrasing.

Usage:
  python eval/real_tender_eval.py <files or folders> [--top-k 5] [--misses 25]

Reads PDF (text or scanned), Word, Excel and plain text with the engine's own
extractor. A line counts as a hit when any standard it cites, compared by
number without edition or part, is in the top k. A line too short to describe
goods once its citations are removed is skipped, and each distinct line is
counted once. Runs the engine in-process, on a throwaway accounts database
and with query logging off, so nothing reaches the real usage figures.
"""

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# A citation as tenders write it: "IS 4984", "I.S. 1786", "IS:456", "IS-1239",
# "IS/ISO 4427". The number is kept; part and edition are compared away.
_CITATION = re.compile(r"\bI\.?\s?S\.?\s*(?:/\s*(ISO|IEC)\s*)?[:\-]?\s*(\d{2,5})\b", re.IGNORECASE)
# How an item line starts, in schedules of rates and BOQs: a capitalised verb
# ("Providing and fixing", "Supplying") or an item marker ("Item 3:"). Case
# matters: "water supply" inside a line is not the start of one.
_ITEM_START = re.compile(
    r"\b(?:Providing|Supplying|Supply|Procuring|Procurement|Laying|Fixing|Erection|Installation|Installing|"
    r"Designing|Manufacturing|Construction|Constructing|PROVIDING|SUPPLYING|SUPPLY|P/F|S/F|SITC)\b"
    r"|\bItem\s+\d+\s*[:.\-]", )
# Where one sentence or numbered item ends and the next begins.
_BOUNDARY = re.compile(r"\.\s+(?=[A-Z0-9])|;\s+|\n")
# The citation phrase itself, removed from the query so the engine cannot read the answer.
_CITING_PHRASE = re.compile(
    r"\(?\s*(?:conforming|confirming|conform(?:s)?|as\s+per|according|complying|comply(?:ing)?|in\s+accordance)"
    r"\s+(?:to|with)?\s*(?:the\s+)?(?:relevant\s+|latest\s+)?(?:I\.?\s?S\.?|B\.?I\.?S\.?)[^,;.)]*\)?",
    re.IGNORECASE)
_BARE = re.compile(r"\bI\.?\s?S\.?\s*(?:/\s*(?:ISO|IEC)\s*)?[:\-]?\s*\d{2,5}(?:\s*\((?:part|pt)[^)]*\))?"
                   r"(?:\s*[:/\-]\s*\d{4})?", re.IGNORECASE)
MIN_QUERY_CHARS = 25


def base_number(number):
    """'IS 694 (Part 2):2016' -> 'IS 694'; 'IS/ISO 4427-2:2007' -> 'IS/ISO 4427'."""
    m = re.match(r"\s*(IS(?:\s*/\s*(?:ISO|IEC))?)\s*[:\-]?\s*(\d+)", number or "", re.IGNORECASE)
    if not m:
        return None
    prefix = re.sub(r"\s+", "", m.group(1)).upper()
    return f"{prefix} {m.group(2)}"


def cited(segment):
    return {f"IS/{m.group(1).upper()} {m.group(2)}" if m.group(1) else f"IS {m.group(2)}"
            for m in _CITATION.finditer(segment)}


def as_query(segment):
    text = _CITING_PHRASE.sub(" ", segment)
    text = _BARE.sub(" ", text)
    text = re.sub(r"\(\s*\)", " ", text)
    return " ".join(text.split()).strip(" ,;.-")[:600]


def lines_with_citations(text):
    """(query, cited standards) for each item line that cites an IS number.

    The line runs from the first item start after the last sentence boundary
    before the citation, to the end of the sentence the citation is in. A
    citation with no item start since the last boundary is a note ("the design
    shall be in accordance with IS 456"), not an item, and is skipped.
    """
    flat = " ".join(text.split())
    seen, out = set(), []
    for m in _CITATION.finditer(flat):
        window_start = max(0, m.start() - 700)
        window = flat[window_start:m.start()]
        boundaries = list(_BOUNDARY.finditer(window))
        after = boundaries[-1].end() if boundaries else 0
        first_start = _ITEM_START.search(window, after)
        if first_start is None:
            continue
        start = window_start + first_start.start()
        end_match = re.search(r"\.\s+(?=[A-Z0-9])", flat[m.end():m.end() + 300])
        end = m.end() + (end_match.start() + 1 if end_match else 300)
        segment = flat[start:end]
        query = as_query(segment)
        labels = cited(segment)
        key = query.lower()
        if len(query) < MIN_QUERY_CHARS or not labels or key in seen:
            continue
        seen.add(key)
        out.append((query, labels))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--misses", type=int, default=25)
    args = ap.parse_args()

    os.environ.setdefault("STANDARDS_CORPUS", "full")
    os.environ["AUTH_REQUIRED"] = "0"
    os.environ["EXPLANATION_WARMUP"] = "0"
    os.environ["ACCOUNTS_DB"] = str(Path(tempfile.mkdtemp(prefix="tender-eval-")) / "accounts.db")
    os.chdir(_ROOT)

    import extraction
    import main as engine
    from fastapi.testclient import TestClient

    engine.append_query = lambda *a, **k: None

    files = []
    for p in map(Path, args.paths):
        files += sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [p]

    items = []
    for f in files:
        try:
            text = extraction.extract(f.name, f.read_bytes()).text
        except extraction.ExtractionError as exc:
            print(f"skipped {f.name}: {exc}")
            continue
        found = lines_with_citations(text)
        print(f"{f.name}: {len(found)} lines citing an IS number")
        items += [(f.name, q, labels) for q, labels in found]

    if not items:
        print("No tender lines with IS citations were found.")
        return 1

    top1 = topk = 0
    misses = []
    with TestClient(engine.app) as client:
        for name, query, labels in items:
            data = client.post("/retrieve", json={"query": query, "top_k": args.top_k}).json()
            got = [base_number(r["number"]) for r in data.get("results", [])]
            wanted = {base_number(label) for label in labels}
            if got and got[0] in wanted:
                top1 += 1
            if any(g in wanted for g in got[:args.top_k]):
                topk += 1
            else:
                misses.append((name, query, sorted(wanted), [r["number"] for r in data.get("results", [])][:3]))

    n = len(items)
    print(f"\n{n} tender lines: cited standard first {top1}/{n} ({top1 / n:.0%}), "
          f"in the top {args.top_k} {topk}/{n} ({topk / n:.0%})")
    for name, query, wanted, got in misses[:args.misses]:
        print(f"  MISS [{name}] {query[:110]!r}\n       cited {wanted}, got {got}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
