"""Generate an evaluation set sized for the corpus it measures.

The existing eval set is 24 queries, written alongside a 30-standard corpus.
At a few thousand standards that is far too small to measure anything: a
single query flipping moves P@1 by four percentage points, and 24 queries
cannot cover 17 sectors.

Queries here are derived from each standard's own title, in the way a
procurement official would actually phrase a request — not copied verbatim,
because a query identical to the title measures string matching rather than
retrieval.

This is still a weak eval set in one respect, and it is worth being explicit:
the queries are derived from the documents, so they share vocabulary with
them. A genuinely independent set would be written by procurement officers
who had never seen the corpus. This is a stopgap that is honest about being
one.

Run with::

    python data/build_eval_set.py --corpus full --size 300
"""

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Noise words that appear in titles but never in how someone asks for a thing.
_DROP = re.compile(
    r"\b(specification|specifications|code of practice|methods? of test|"
    r"part\s*\d+|section\s*\d+|first|second|third|fourth|fifth|revision|"
    r"indian standard|glossary|requirements?)\b",
    re.IGNORECASE,
)

# How a procurement official opens a request.
_PREFIXES = [
    "{}",
    "{} for procurement",
    "standard for {}",
    "which standard covers {}",
    "{} specification required",
    "supply of {}",
]


def query_from_title(title: str, rng: random.Random) -> str:
    """Turn a standard's title into something a person would type."""
    text = _DROP.sub(" ", title)
    text = re.sub(r"[-—:,()]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    words = text.split()
    if len(words) > 9:
        # Long titles get trimmed; nobody types twenty words.
        words = words[:9]

    # Trimming and word-removal both leave dangling prepositions: "methods of
    # test for soils" becomes "for soils", and a truncated title ends "...
    # specific for". Strip them from both ends so the query reads like
    # something a person would actually type.
    _EDGE = {"for", "of", "and", "with", "in", "to", "the", "a", "an", "on", "its", "by", "or"}
    while words and words[0].lower() in _EDGE:
        words.pop(0)
    while words and words[-1].lower() in _EDGE:
        words.pop()

    text = " ".join(words).strip().lower()

    if len(text) < 8 or len(words) < 2:
        return ""
    return rng.choice(_PREFIXES).format(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default="full", help="corpus alias: full | expanded | canonical")
    parser.add_argument("--size", type=int, default=300, help="how many queries to generate")
    parser.add_argument("--seed", type=int, default=20260921, help="for reproducibility")
    args = parser.parse_args()

    paths = {
        "full": _REPO_ROOT / "data" / "standards_corpus_full.json",
        "expanded": _REPO_ROOT / "data" / "standards_corpus_expanded.json",
        "canonical": _REPO_ROOT / "data" / "standards_corpus.json",
    }
    source = paths[args.corpus]
    corpus = json.loads(source.read_text(encoding="utf-8"))

    rng = random.Random(args.seed)

    # Spread across sectors rather than sampling uniformly, so a sector with
    # 2,000 standards does not drown out one with 12.
    by_sector = defaultdict(list)
    for record in corpus:
        by_sector[record["category"]].append(record)

    per_sector = max(1, args.size // len(by_sector))
    chosen = []
    for sector, records in sorted(by_sector.items()):
        rng.shuffle(records)
        chosen.extend(records[:per_sector])

    rng.shuffle(chosen)
    chosen = chosen[: args.size]

    queries = []
    skipped = 0
    for record in chosen:
        query = query_from_title(record["title"], rng)
        if not query:
            skipped += 1
            continue
        queries.append(
            {
                "query": query,
                "correct_id": record["id"],
                "correct_number": record["number"],
                "category": record["category"],
            }
        )

    # Split: the eval set must never be trained on, so it is written separately
    # and the trainer only reads the train file by default.
    split = int(len(queries) * 0.6)
    train, evaluate = queries[:split], queries[split:]

    suffix = {"full": "full", "expanded": "expanded", "canonical": "consolidated"}[args.corpus]
    train_path = _REPO_ROOT / "data" / f"train_queries_{suffix}.json"
    eval_path = _REPO_ROOT / "data" / f"eval_set_{suffix}.json"

    train_path.write_text(json.dumps(train, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    eval_path.write_text(json.dumps(evaluate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    from collections import Counter

    print(f"corpus        : {len(corpus)} standards, {len(by_sector)} sectors")
    print(f"generated     : {len(queries)} queries ({skipped} titles too short to use)")
    print(f"  train       : {len(train)} -> {train_path.name}")
    print(f"  eval        : {len(evaluate)} -> {eval_path.name}")
    print("per sector:")
    for sector, count in sorted(Counter(q["category"] for q in queries).items()):
        print(f"  {sector:<28} {count:>4}")
    print("\nsample queries:")
    for q in queries[:5]:
        print(f"  {q['query'][:66]:<68} -> {q['correct_number']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
