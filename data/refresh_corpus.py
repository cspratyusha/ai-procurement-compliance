"""Rebuild everything the website serves, from ingested data to live indexes.

Scraping standards does not change what the website shows. Four things have to
happen, and skipping any one of them leaves the site serving the old corpus:

  1. ingest      archive.org  ->  data/archive/ingested_standards.json
  2. merge       ingested + curated  ->  data/standards_corpus_full.json
  3. index       corpus  ->  FAISS + BM25 for that corpus
  4. restart     the API process, which loads its corpus once at startup

This script does 2 and 3, and tells you to do 4. Step 1 is separate because it
is slow and rate-limited; run `data/ingest_archive.py` for that.

Run with::

    python data/refresh_corpus.py
"""

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYTHON = sys.executable


def run(label: str, args: list, env_extra: dict = None) -> bool:
    import os

    print(f"\n=== {label} ===", flush=True)
    env = {**os.environ, **(env_extra or {})}
    result = subprocess.run(args, cwd=_REPO_ROOT, env=env)
    if result.returncode != 0:
        print(f"FAILED: {label}")
        return False
    return True


def main() -> int:
    ingested = _REPO_ROOT / "data" / "archive" / "ingested_standards.json"
    if not ingested.exists():
        print(
            "No ingested data found. Run this first:\n"
            "  python data/ingest_archive.py --limit 10000"
        )
        return 1

    if not run("2. merge into the full corpus", [_PYTHON, "data/build_full_corpus.py"]):
        return 1

    if not run(
        "3. build FAISS + BM25 indexes",
        [_PYTHON, "standards-retrieval/indexing/build.py"],
        {"STANDARDS_CORPUS": "full", "PYTHONPATH": str(_REPO_ROOT / "standards-retrieval")},
    ):
        return 1

    import json

    corpus = json.loads(
        (_REPO_ROOT / "data" / "standards_corpus_full.json").read_text(encoding="utf-8")
    )

    print(f"\n=== 4. restart the API ===")
    print("The running server loaded its corpus at startup, so it will keep")
    print("serving the old one until restarted. Stop it, then:\n")
    print("  STANDARDS_CORPUS=full .venv/Scripts/python -m uvicorn main:app \\")
    print("    --port 8000 --app-dir standards-retrieval\n")
    print(f"/health should then report corpus_size: {len(corpus)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
