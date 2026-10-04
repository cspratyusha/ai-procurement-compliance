"""Keep the served corpus current with BIS while the engine runs.

There is no scheduled task: the corpus is refreshed when the engine is
running, which is when its answers matter. At startup, if the last complete
refresh is older than BIS_REFRESH_DAYS (7), or none has completed, a
background thread runs the refresh while the engine keeps serving the corpus
it loaded:

  1. data/bis_portal.py published   what BIS published or revised since the
                                    Know Your Standard snapshot, then scopes
                                    (each new one's SCOPE clause)
  2. data/bis_portal.py details     each served edition's current record;
                                    any older than 30 days is read again,
                                    which is how withdrawals and new
                                    amendments are noticed
  3. data/bis_portal.py combine, then summaries (BIS's plain-language
                                    summary of each standard, 3,000 new
                                    look-ups per refresh)
     then BIS's compulsory-certification lists (parse_bis_compulsory.py --fetch)
  4. build_full_corpus.py, add_bis_standards.py, apply_bis_status.py
  5. indexing/build.py              the dense and BM25 indexes

When every step has succeeded the engine swaps in the new corpus and indexes
without a restart (on_success). The corpus, query sets and indexes are copied
aside before step 4 and put back if a later step fails, so a failed refresh
never leaves a corpus and an index that disagree. One refresh runs at a time,
across processes (a lock file).

Only the full corpus is refreshed. BIS_AUTO_REFRESH=0 turns it off; the test
suite and the evaluation scripts do. Progress is in /health and in
data/archive/bis_refresh.log.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("standards-retrieval.bis_refresh")

_ROOT = Path(__file__).resolve().parent
_REPO = _ROOT.parent
_DATA = _REPO / "data"
_STATE = _DATA / "archive" / "bis_refresh_state.json"
_LOG = _DATA / "archive" / "bis_refresh.log"
_LOCK = _DATA / "archive" / "bis_refresh.lock"
_BACKUP = _DATA / "archive" / "backup" / "bis_refresh"
_INDEX_DIR = _ROOT / "data" / "index" / "standards_corpus_full"
_GUARDED = [_DATA / "standards_corpus_full.json", _DATA / "eval_set_full.json", _DATA / "train_queries_full.json"]
_STALE_LOCK_S = 8 * 3600
_RECHECK_DAYS = "30"
_SUMMARY_BATCH = "3000"

_status = {"state": "idle", "step": None, "started": None, "error": None}
_lock = threading.Lock()


def enabled() -> bool:
    return (os.environ.get("BIS_AUTO_REFRESH", "1") != "0"
            and os.environ.get("STANDARDS_CORPUS", "mock").lower() == "full")


def interval_days() -> float:
    return float(os.environ.get("BIS_REFRESH_DAYS", "7"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _state() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(**fields) -> None:
    """Merge fields into the saved state; a field set to None is removed."""
    state = {k: v for k, v in {**_state(), **fields}.items() if v is not None}
    _STATE.write_text(json.dumps(state), encoding="utf-8")


def last_completed() -> Optional[str]:
    return _state().get("last_completed")


def recover() -> bool:
    """Put back the corpus and index if the engine stopped mid-refresh.

    Steps 4 and 5 rewrite the served files; if the engine was closed between
    them, the corpus on disk and the index no longer agree. Called at startup,
    before anything is loaded. Returns whether it restored anything.
    """
    if not _state().get("applying_since") or not _BACKUP.exists():
        return False
    _restore()
    _save_state(applying_since=None)
    try:
        _LOCK.unlink()
    except OSError:
        pass
    _log("the engine stopped during the last refresh; restored the corpus and index from before it")
    logger.warning("[BIS refresh] An interrupted refresh was rolled back.")
    return True


def due() -> bool:
    done = last_completed()
    if not done:
        return True
    age = datetime.now(timezone.utc) - datetime.fromisoformat(done)
    return age.total_seconds() > interval_days() * 86400


def status() -> dict:
    with _lock:
        return {**_status, "enabled": enabled(), "last_completed": last_completed(),
                "interval_days": interval_days()}


def _set(**fields) -> None:
    with _lock:
        _status.update(fields)


def _log(line: str) -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {line}\n")


def _take_lock() -> bool:
    """One refresh at a time, also across engine processes. A lock older than
    any refresh takes is from a process that died and is taken over."""
    try:
        if _LOCK.exists() and time.time() - _LOCK.stat().st_mtime > _STALE_LOCK_S:
            _LOCK.unlink()
        fd = os.open(str(_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{os.getpid()} {_now()}".encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _run(label: str, args: list, env_extra: Optional[dict] = None) -> None:
    _set(step=label)
    _log(f"=== {label} ===")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1", **(env_extra or {})}
    with _LOG.open("a", encoding="utf-8") as out:
        code = subprocess.run([sys.executable, *args], cwd=_REPO, env=env,
                              stdout=out, stderr=subprocess.STDOUT).returncode
    if code != 0:
        raise RuntimeError(f"{label} failed (exit {code}); see {_LOG.name}")
    _log(f"done: {label}")


def _back_up() -> None:
    if _BACKUP.exists():
        shutil.rmtree(_BACKUP)
    (_BACKUP / "index").mkdir(parents=True)
    for path in _GUARDED:
        shutil.copy2(path, _BACKUP / path.name)
    for path in _INDEX_DIR.iterdir():
        shutil.copy2(path, _BACKUP / "index" / path.name)


def _restore() -> None:
    for path in _GUARDED:
        shutil.copy2(_BACKUP / path.name, path)
    for path in (_BACKUP / "index").iterdir():
        shutil.copy2(path, _INDEX_DIR / path.name)


def refresh(on_success: Optional[Callable[[], None]] = None) -> bool:
    """Run every step; True when the new corpus is in place (and served)."""
    if not _take_lock():
        _log("another refresh is running; not starting a second")
        return False
    _set(state="running", started=_now(), error=None, step=None)
    _log("BIS refresh started")
    backed_up = False
    try:
        _run("portal: published since the snapshot", ["data/bis_portal.py", "published"])
        # The scope clause of each newly published standard, from its document
        # (only those not read before).
        _run("portal: scopes", ["data/bis_portal.py", "scopes"])
        _run("portal: records", ["data/bis_portal.py", "details", "--recheck-days", _RECHECK_DAYS])
        _run("portal: combine", ["data/bis_portal.py", "combine"])
        # BIS's summaries are looked up once per standard, a batch per refresh,
        # so the whole catalogue is covered over a few weeks of use.
        _run("portal: summaries", ["data/bis_portal.py", "summaries", "--limit", _SUMMARY_BATCH])
        # BIS's lists of products under compulsory certification, which change
        # whenever a Quality Control Order is notified. The previous list is
        # kept if a page comes back in a shape the parser does not read.
        _run("certification lists", ["data/certification/parse_bis_compulsory.py", "--fetch"])
        _set(step="backing up the served corpus and index")
        _back_up()
        backed_up = True
        _save_state(applying_since=_now())
        _run("merge", ["data/build_full_corpus.py"])
        _run("add BIS standards", ["data/add_bis_standards.py"])
        _run("apply BIS status", ["data/apply_bis_status.py"])
        _run("index", ["standards-retrieval/indexing/build.py"],
             {"STANDARDS_CORPUS": "full", "PYTHONPATH": str(_ROOT)})
        _save_state(last_completed=_now(), applying_since=None)
        if on_success:
            _set(step="loading the new corpus")
            on_success()
        _set(state="idle", step=None)
        _log("BIS refresh complete; the engine now serves the new corpus")
        return True
    except Exception as exc:  # noqa: BLE001 -- reported in /health and the log
        logger.error("[BIS refresh] %s", exc)
        _log(f"FAILED: {exc}")
        if backed_up:
            _restore()
            _save_state(applying_since=None)
            _log("restored the corpus and index from before the refresh")
        _set(state="failed", error=str(exc), step=None)
        return False
    finally:
        try:
            _LOCK.unlink()
        except OSError:
            pass


def start_if_due(on_success: Optional[Callable[[], None]] = None) -> bool:
    """Start a background refresh when one is due. Returns whether it started."""
    if not enabled() or not due():
        return False
    thread = threading.Thread(target=refresh, args=(on_success,), name="bis-refresh", daemon=True)
    thread.start()
    logger.info("[BIS refresh] Started in the background (last complete refresh: %s).",
                last_completed() or "never")
    return True


if __name__ == "__main__":
    # A refresh by hand, without the engine: python standards-retrieval/bis_refresh.py
    # A running engine keeps serving its corpus until it is restarted.
    logging.basicConfig(level=logging.INFO)
    os.environ.setdefault("STANDARDS_CORPUS", "full")
    if recover():
        print("Rolled back an interrupted refresh first.")
    ok = refresh()
    print("BIS refresh", "complete" if ok else f"did not complete; see {_LOG}")
    sys.exit(0 if ok else 1)
