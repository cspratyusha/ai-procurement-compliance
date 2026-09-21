"""Merge, index and restart the API in one command.

Ingestion writes to a file. The API reads a *different* file, once, at
startup. So scraping more standards changes nothing a user can see until:

    merge  ->  index  ->  restart

`refresh_corpus.py` does the first two and then tells you to do the third by
hand, which is exactly the step that gets forgotten. This does all three, so
"more standards were ingested" and "the site shows more standards" stay the
same statement.

Safe to run repeatedly while ingestion is still going: it picks up whatever
has been written so far.

Run with::

    python data/refresh_and_serve.py
    python data/refresh_and_serve.py --no-restart   # merge and index only
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYTHON = sys.executable
_RETRIEVAL = _REPO_ROOT / "standards-retrieval"
_HEALTH = "http://127.0.0.1:8000/health"


def health() -> dict:
    try:
        with urllib.request.urlopen(_HEALTH, timeout=4) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}


def stop_server() -> None:
    """Stop whatever is holding port 8000.

    The API caches its corpus in memory, so it has to be restarted; there is
    no reload hook. On Windows this is a PowerShell one-liner.
    """
    if os.name == "nt":
        subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "$p = (Get-NetTCPConnection -LocalPort 8000 -State Listen "
                "-ErrorAction SilentlyContinue).OwningProcess; "
                "if ($p) { Stop-Process -Id $p -Force }",
            ],
            capture_output=True,
        )
    else:
        subprocess.run(["pkill", "-f", "uvicorn main:app"], capture_output=True)
    time.sleep(2)


def start_server() -> bool:
    """Start the API on the full corpus and wait for it to answer."""
    env = {
        **os.environ,
        "STANDARDS_CORPUS": "full",
        "PYTHONPATH": str(_RETRIEVAL),
    }
    log = _REPO_ROOT / "data" / "archive" / "api.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    with log.open("w", encoding="utf-8") as handle:
        subprocess.Popen(
            [
                _PYTHON, "-m", "uvicorn", "main:app",
                "--port", "8000", "--app-dir", "standards-retrieval",
            ],
            cwd=_REPO_ROOT,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )

    # Loading two transformer models takes ~20 s from cold.
    print("  waiting for the API (model loading takes ~20 s)...", flush=True)
    for _ in range(60):
        time.sleep(3)
        state = health()
        if state:
            print(f"  API up: {state['corpus_size']} standards", flush=True)
            return True
    print("  API did not come up; see data/archive/api.log")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-restart", action="store_true", help="merge and index only")
    args = parser.parse_args()

    before = health().get("corpus_size")

    ingested = _REPO_ROOT / "data" / "archive" / "ingested_standards.json"
    if not ingested.exists():
        print("No ingested data yet. Run data/ingest_archive.py first.")
        return 1

    print("=== merge ===", flush=True)
    if subprocess.run([_PYTHON, "data/build_full_corpus.py"], cwd=_REPO_ROOT).returncode:
        return 1

    print("\n=== index ===", flush=True)
    env = {**os.environ, "STANDARDS_CORPUS": "full", "PYTHONPATH": str(_RETRIEVAL)}
    if subprocess.run(
        [_PYTHON, "standards-retrieval/indexing/build.py"], cwd=_REPO_ROOT, env=env
    ).returncode:
        return 1

    corpus = json.loads(
        (_REPO_ROOT / "data" / "standards_corpus_full.json").read_text(encoding="utf-8")
    )

    if args.no_restart:
        print(f"\nCorpus and indexes rebuilt: {len(corpus)} standards.")
        print("The API still serves its old corpus until restarted.")
        return 0

    print("\n=== restart ===", flush=True)
    stop_server()
    if not start_server():
        return 1

    after = health().get("corpus_size")
    if before is not None:
        print(f"\nsite went from {before} to {after} standards")
    else:
        print(f"\nsite now serving {after} standards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
