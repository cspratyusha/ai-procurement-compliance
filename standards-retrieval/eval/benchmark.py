"""Accuracy on the fixed buyer-language benchmark, overall and per language.

data/benchmark_queries.json holds everyday procurement queries in English and
the same items in 12 Indian languages, each with the standards that answer
it. Earlier spot checks were run from queries typed at the time and never
saved, so their figures could not be reproduced after a change; this set is
committed so they can.

Every query is searched as a user would send it: language detected, not
declared. Reported per language: the right standard first, in the top five,
whether the language was detected correctly, and what was actually searched
after translation, since a miss in another language is usually a
translation miss.

Usage:
  python eval/benchmark.py [--lang hi,ta] [--top-k 5] [--out results.json] [--misses 40]

Runs the engine in-process on a throwaway accounts database with query
logging off, so nothing reaches the real usage figures.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_QUERIES = _ROOT.parent / "data" / "benchmark_queries.json"
sys.path.insert(0, str(_ROOT))


def standard(number):
    """'IS 694 (Part 2):2016' -> 'IS 694 (PART 2)': the standard, any edition."""
    text = " ".join((number or "").upper().split())
    text = re.sub(r"\s*:\s*\d{4}.*$", "", text)
    return re.sub(r"\(\s*PART\s*", "(PART ", text)


def answers(result_number, expected):
    """True when the result is an expected standard, or a part of one listed
    without a part. 'IS 1239' does not accept 'IS 12390'."""
    got = standard(result_number)
    for want in map(standard, expected):
        if got == want or got.startswith(want + " ("):
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", help="only these languages, comma separated")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--out", help="write per-query results as JSON")
    ap.add_argument("--misses", type=int, default=40)
    args = ap.parse_args()

    os.environ.setdefault("STANDARDS_CORPUS", "full")
    os.environ["AUTH_REQUIRED"] = "0"
    os.environ["EXPLANATION_WARMUP"] = "0"
    os.environ["BIS_AUTO_REFRESH"] = "0"
    os.environ["ACCOUNTS_DB"] = str(Path(tempfile.mkdtemp(prefix="benchmark-")) / "accounts.db")
    os.chdir(_ROOT)

    import main as engine
    from fastapi.testclient import TestClient

    engine.append_query = lambda *a, **k: None

    items = json.loads(_QUERIES.read_text(encoding="utf-8"))["queries"]
    if args.lang:
        wanted = set(args.lang.split(","))
        items = [q for q in items if q["lang"] in wanted]

    rows = []
    with TestClient(engine.app) as client:
        corpus = client.get("/health").json().get("corpus_size")
        for item in items:
            data = client.post("/retrieve", json={"query": item["query"], "top_k": args.top_k}).json()
            results = [r["number"] for r in data.get("results", [])]
            info = data.get("translation") or {}
            rows.append({
                **item,
                "searched": info.get("translated_text") or item["query"],
                "detected": info.get("detected_language") or info.get("detected") or "en",
                "confidence": data.get("confidence"),
                "results": results,
                "first": bool(results) and answers(results[0], item["expect"]),
                "top_k": any(answers(r, item["expect"]) for r in results[:args.top_k]),
            })

    by_lang = defaultdict(list)
    for row in rows:
        by_lang[row["lang"]].append(row)

    print(f"\nBenchmark on {corpus} records, top {args.top_k}")
    print(f"{'lang':6}{'n':>4}{'first':>9}{'top-k':>9}{'detected':>10}")
    for lang, group in by_lang.items():
        n = len(group)
        detected = sum(1 for r in group if r["detected"] == lang)
        print(f"{lang:6}{n:>4}{sum(r['first'] for r in group):>6}/{n:<2}{sum(r['top_k'] for r in group):>6}/{n:<2}"
              f"{detected:>7}/{n:<2}")
    other = [r for r in rows if r["lang"] != "en"]
    english = by_lang.get("en", [])
    for label, group in (("English", english), ("Other languages", other), ("All", rows)):
        if group:
            n = len(group)
            print(f"{label}: first {sum(r['first'] for r in group)}/{n} "
                  f"({sum(r['first'] for r in group) / n:.0%}), top {args.top_k} "
                  f"{sum(r['top_k'] for r in group)}/{n} ({sum(r['top_k'] for r in group) / n:.0%})")

    misses = [r for r in rows if not r["first"]]
    if misses:
        print(f"\nNot first ({len(misses)}):")
    for r in misses[:args.misses]:
        mark = "top-k" if r["top_k"] else "MISS "
        searched = f" -> {r['searched']!r}" if r["searched"] != r["query"] else ""
        print(f"  {mark} [{r['lang']}] {r['query']!r}{searched}\n         want {r['expect']}, got {r['results'][:3]}")

    if args.out:
        Path(args.out).write_text(json.dumps({"corpus_size": corpus, "rows": rows}, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
