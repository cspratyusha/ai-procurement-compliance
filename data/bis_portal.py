"""BIS's new standards portal: what was published, withdrawn and amended after
the Know Your Standard snapshot.

BIS's Know Your Standard pages (data/bis_kys.py) stop at 1 October 2025;
standards published after that are on the new portal at
https://standards.bis.gov.in. The portal is a browser application backed by a
public JSON API, the same calls its own pages make without signing in:

  master-service/getNewStandardsList       standards published for the first
  master-service/getRevisedStandardsList   time, and revisions, per technical
                                           department and date range
  review-service/searchKnowStandards       a standard by number: publication
                                           date, validity, withdrawn and when
  review-service/getAmendmentDetails       every amendment with its year

Three steps, each resumable:

  published  every standard published or revised in a date range (default:
             1 October 2025 to today), page by page for each department
  details    for each standard asked about, BIS's current record: withdrawn
             (and the date), and the amendments with their years. By default
             the current editions in the served corpus plus everything
             `published` found. One record per standard is kept under
             data/archive/portal_cache/ (not committed), so a run that stops
             resumes where it left off
  combine    writes data/amendments/bis_portal.json

Requests are paced (a pause after each, a few in parallel at most), as for the
Know Your Standard pages.

Usage:
  python data/bis_portal.py published [--from 2025-10-01] [--to YYYY-MM-DD]
  python data/bis_portal.py details [--workers 3] [--delay 0.4] [--limit N] [--only-amended] [--recheck-days 30]
  python data/bis_portal.py combine
  python data/bis_portal.py summaries [--limit N] [--workers 2]
  python data/bis_portal.py scopes [--limit N]

  scopes     the SCOPE clause of each standard published since the snapshot,
             from the document BIS's portal links; only the clause is kept,
             in data/bis_scopes.json

  summaries  BIS's one-page summary of each current standard where it
             publishes one, certification standards first, each looked up
             once; written to data/bis_summaries.json
"""

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from text_repair import fix_text  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE = _REPO_ROOT / "data" / "archive" / "portal_cache"
PUBLISHED = CACHE / "published.json"
OUTPUT = _REPO_ROOT / "data" / "amendments" / "bis_portal.json"
CORPUS = _REPO_ROOT / "data" / "standards_corpus_full.json"
KYS = _REPO_ROOT / "data" / "amendments" / "bis_kys.json"

PORTAL = "https://standards.bis.gov.in"
MASTER = "https://standardsadmin.bis.gov.in/master-service"
REVIEW = "https://standardsadmin.bis.gov.in/review-service"
PROJECT = "https://standardsadmin.bis.gov.in/project-service"
SNAPSHOT_END = "2025-10-01"   # where the Know Your Standard record stops
PAGE_SIZE = 100               # the most the list calls return per page
HEADERS = {
    "Content-Type": "application/json",
    "Origin": PORTAL,
    "Referer": PORTAL + "/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StandEng standards research",
}

_ORDINALS = {w: i for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth "
    "fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth".split(), 1)}


def post(url: str, body: dict, attempts: int = 4) -> dict:
    data = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001 -- retried, then raised
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def number_key(number: str) -> str:
    """'IS 1239 ( Part 1 ) : 2004' and 'IS 1239 (PART 1):2004' compare equal."""
    text = " ".join((number or "").replace("\\/", "/").split())
    text = re.sub(r"\(\s*", "(", text)
    text = re.sub(r"\s*\)", ")", text)
    text = re.sub(r"\s*:\s*", ":", text)
    text = re.sub(r"\s*/\s*", "/", text)
    return text.upper()


def tidy_number(number: str) -> str:
    """BIS's spelling made consistent with the corpus: 'IS 101 (PART 1/SEC 2):2023'
    becomes 'IS 101 (Part 1/Sec 2):2023'."""
    text = " ".join((number or "").replace("\\/", "/").split())
    text = re.sub(r"\(\s*", "(", text)
    text = re.sub(r"\s*\)", ")", text)
    text = re.sub(r"\s*:\s*", ":", text)
    text = re.sub(r"(?i)\bpart\b", "Part", text)
    text = re.sub(r"(?i)\bsec\b", "Sec", text)
    return text


# --- published: what appeared after the snapshot -------------------------------

def departments() -> list:
    reply = post(f"{PROJECT}/getWebsiteTechnicalDepartments", {})
    return [(d["departmentId"], d.get("deptAliasName") or d.get("deptName")) for d in reply.get("data") or []]


def published(start: str, end: str, delay: float) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    found = {}
    for dept_id, dept in departments():
        for kind, call in (("new", "getNewStandardsList"), ("revised", "getRevisedStandardsList")):
            page, last_page = 1, 1
            while page <= last_page:
                reply = post(f"{MASTER}/{call}", {"departmentId": dept_id, "page": page,
                                                  "per_page": PAGE_SIZE, "fromDate": start, "toDate": end})
                if reply.get("status") != "SUCCESS":
                    break
                for item in reply.get("data") or []:
                    number = tidy_number(item.get("standardNumber"))
                    if not re.match(r"^(?:IS|SP)\b", number):
                        continue   # bulletins ("SI B2410:2011") share the list
                    found.setdefault(number_key(number), {
                        "number": number,
                        "title": fix_text(" ".join((item.get("standardName") or "").split())),
                        "published_on": item.get("publishedOn"),
                        "kind": kind,
                        "type": item.get("typeOfStandardName"),
                        "department": dept,
                        "standard_id": item.get("standardId"),
                        # The published standard itself, which BIS makes free to read.
                        "document": item.get("is_documents") or None,
                    })
                last_page = (reply.get("pagination") or {}).get("last_page") or 1
                page += 1
                time.sleep(delay)
        print(f"{dept}: {len(found)} so far", flush=True)
    PUBLISHED.write_text(json.dumps({"from": start, "to": end, "retrieved": date.today().isoformat(),
                                     "standards": found}, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds = {k: sum(1 for s in found.values() if s["kind"] == k) for k in ("new", "revised")}
    print(f"published {start} to {end}: {len(found)} standards {kinds} -> {PUBLISHED}")


# --- details: BIS's current record for one standard -----------------------------

def _amendment_number(label: str, position: int) -> int:
    word = (label or "").split(" ")[0].lower()
    if word in _ORDINALS:
        return _ORDINALS[word]
    m = re.search(r"\d+", label or "")
    return int(m.group(0)) if m else position


def _amendments(enc_id: str) -> list:
    reply = post(f"{REVIEW}/getAmendmentDetails", {"standardId": enc_id})
    if reply.get("status") != "SUCCESS":
        return []
    rows = reply.get("data") or []
    out = []
    for i, row in enumerate(rows, 1):
        year = re.search(r"(19|20)\d{2}", str(row.get("amendmentYear") or ""))
        out.append({"number": _amendment_number(row.get("amendmentLabel"), i),
                    "label": row.get("amendmentLabel"),
                    "year": int(year.group(0)) if year else None})
    return sorted(out, key=lambda a: a["number"])


def detail(number: str, want_amendments: bool) -> dict:
    """BIS's current record for one edition, or {"found": False}."""
    reply = post(f"{REVIEW}/searchKnowStandards", {"searchText": number})
    key = number_key(number)
    matches = [d for d in reply.get("data") or [] if number_key(d.get("standardNumber")) == key]
    if not matches:
        return {"number": number, "found": False}
    # BIS sometimes holds two records for one edition (a reprint and the
    # original); a withdrawal on either counts, and the amendments are read
    # from whichever lists more.
    withdrawn = [m for m in matches if m.get("withdrawStatus") == 1]
    record = {
        "number": number,
        "found": True,
        "withdrawn": bool(withdrawn),
        "withdrawn_on": (withdrawn[0].get("withdrawOn") or "")[:10] or None if withdrawn else None,
        "published_on": min((m["publishedOn"] for m in matches if m.get("publishedOn")), default=None),
        "valid_upto": max((m["validUpto"] for m in matches if m.get("validUpto")), default=None),
        "standard_id": matches[0].get("standardId"),
    }
    if want_amendments:
        best = []
        for m in matches:
            found = _amendments(m["standardEncId"]) if m.get("standardEncId") else []
            if len(found) > len(best):
                best = found
        record["amendments"] = best
        record["amendment_count"] = len(best)
    return record


def _cache_path(number: str) -> Path:
    return CACHE / "details" / (re.sub(r"[^A-Za-z0-9]+", "_", number_key(number)).strip("_") + ".json")


def fetch_detail(number: str, want_amendments: bool, delay: float, recheck_days: float = 0) -> str:
    path = _cache_path(number)
    if path.exists() and not (recheck_days and time.time() - path.stat().st_mtime > recheck_days * 86400):
        return "cached"
    try:
        record = detail(number, want_amendments)
    except Exception as exc:  # noqa: BLE001 -- reported, retried on the next run
        return f"failed: {exc}"
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    time.sleep(delay)
    return "found" if record["found"] else "not_found"


def targets(only_amended: bool) -> list:
    """[(number, want_amendments)] for what `published` found, then the
    current editions served. Amendments are asked for where BIS's older record
    counted any, and for anything it never saw.

    Ordered by what the run is for, since a full run takes hours: the
    standards published since the snapshot first, then the amended ones
    (their dates), then the rest (whether BIS has withdrawn them since)."""
    kys = {}
    if KYS.exists():
        kys = {number_key(k): v for k, v in json.loads(KYS.read_text(encoding="utf-8"))["standards"].items()}
    out = {}
    if PUBLISHED.exists():
        for item in json.loads(PUBLISHED.read_text(encoding="utf-8"))["standards"].values():
            out[item["number"]] = (0, True)
    for record in json.loads(CORPUS.read_text(encoding="utf-8")):
        if record.get("status") != "active":
            continue
        old = kys.get(number_key(record["number"]))
        amended = old is None or bool(old.get("amendment_count"))
        if only_amended and not amended:
            continue
        out.setdefault(record["number"], (1 if amended else 2, amended))
    return [(n, amend) for n, (_, amend) in sorted(out.items(), key=lambda kv: kv[1][0])]


def details(workers: int, delay: float, limit: int, only_amended: bool, recheck_days: float = 0) -> None:
    (CACHE / "details").mkdir(parents=True, exist_ok=True)
    wanted = targets(only_amended)
    if limit:
        wanted = wanted[:limit]
    counts, started = {}, time.time()
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_detail, n, amend, delay, recheck_days) for n, amend in wanted]
        for i, future in enumerate(cf.as_completed(futures), 1):
            status = future.result().split(":")[0]
            counts[status] = counts.get(status, 0) + 1
            if i % 250 == 0:
                print(f"{i}/{len(wanted)} {counts} {i / (time.time() - started):.1f}/s", flush=True)
    print("done", len(wanted), counts, flush=True)


# --- summaries: BIS's plain-language account of a standard ---------------------
#
# BIS publishes a one-page summary for many product standards ("Summary of
# Unplasticized PVC Pipes for Potable Water Supplies (IS 4985)"): what the
# product is, what buyers expect of it, and what the standard sets. It is
# written for consumers, so it reads the way a buyer searches. Found for about
# 7 in 10 standards under compulsory certification and 1 in 15 of the rest, so
# those are looked up first, and the rest a batch per refresh.

SUMMARIES = CACHE / "summaries"
SUMMARY_OUTPUT = _REPO_ROOT / "data" / "bis_summaries.json"
CERTIFICATION = _REPO_ROOT / "data" / "certification" / "bis_compulsory.json"
OBJECT_STORE = "https://bmqsdqljvwgm.compat.objectstorage.ap-mumbai-1.oraclecloud.com"


def _summary_text(pdf: bytes) -> str:
    import pymupdf
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        text = " ".join(page.get_text() for page in document)
    text = re.sub(r"\*\*\s*Summary of[^*]*\*\*", "", text, flags=re.IGNORECASE)   # the heading
    text = fix_text(" ".join(text.replace("**", "").split()))
    return text[:2000]


def summary(number: str) -> dict:
    """BIS's summary for one edition: {"number", "found", "text", "file"}."""
    reply = post(f"{REVIEW}/searchKnowStandards", {"searchText": number})
    key = number_key(number)
    for match in [d for d in reply.get("data") or [] if number_key(d.get("standardNumber")) == key]:
        details = post(f"{REVIEW}/getSummaryDetails", {"standardId": match["standardEncId"]}).get("data") or {}
        path = details.get("file_path")
        if not path:
            continue
        request = urllib.request.Request(f"{OBJECT_STORE}/{path}", headers={"User-Agent": HEADERS["User-Agent"]})
        with urllib.request.urlopen(request, timeout=60) as response:
            text = _summary_text(response.read())
        if text:
            return {"number": number, "found": True, "text": text, "file": path}
    return {"number": number, "found": False}


def _summary_path(number: str) -> Path:
    return SUMMARIES / (re.sub(r"[^A-Za-z0-9]+", "_", number_key(number)).strip("_") + ".json")


def fetch_summary(number: str, delay: float) -> str:
    path = _summary_path(number)
    if path.exists():
        return "cached"
    try:
        record = summary(number)
    except Exception as exc:  # noqa: BLE001 -- reported, retried on the next run
        return f"failed: {exc}"
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    time.sleep(delay)
    return "found" if record["found"] else "none"


def summary_targets() -> list:
    """Current editions served: those under compulsory certification first,
    then those held without a scope clause (where a summary is the only text
    describing the standard), then the rest."""
    listed = set()
    if CERTIFICATION.exists():
        payload = json.loads(CERTIFICATION.read_text(encoding="utf-8"))
        entries = payload.get("entries") or payload.get("standards") or []
        for entry in entries if isinstance(entries, list) else entries.values():
            number = isinstance(entry, dict) and (entry.get("is_number") or entry.get("number"))
            if number:
                listed.add(re.sub(r"\s*:\s*\d{4}.*$", "", number_key(number)))
    records = [r for r in json.loads(CORPUS.read_text(encoding="utf-8")) if r.get("status") == "active"]
    family = lambda n: re.sub(r"\s*:\s*\d{4}.*$", "", number_key(n))
    ordered = sorted(records, key=lambda r: (family(r["number"]) not in listed, bool(r.get("scope")), r["number"]))
    return [r["number"] for r in ordered]


def summaries(workers: int, delay: float, limit: int) -> None:
    """Look up summaries not yet looked up, at most `limit` of them (0: all)."""
    SUMMARIES.mkdir(parents=True, exist_ok=True)
    wanted = [n for n in summary_targets() if not _summary_path(n).exists()]
    if limit:
        wanted = wanted[:limit]
    counts, started = {}, time.time()
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_summary, n, delay) for n in wanted]
        for i, future in enumerate(cf.as_completed(futures), 1):
            status = future.result().split(":")[0]
            counts[status] = counts.get(status, 0) + 1
            if i % 100 == 0:
                print(f"{i}/{len(wanted)} {counts} {i / (time.time() - started):.1f}/s", flush=True)
    found = [json.loads(p.read_text(encoding="utf-8")) for p in SUMMARIES.glob("*.json")]
    found = {r["number"]: {"text": r["text"], "file": r["file"]} for r in found if r.get("found")}
    SUMMARY_OUTPUT.write_text(json.dumps({
        "_meta": {
            "source": "BIS standards portal, standard summaries (" + PORTAL + ")",
            "retrieved": date.today().isoformat(),
            "looked_up": len(list(SUMMARIES.glob("*.json"))),
            "found": len(found),
            "note": "BIS's one-page plain-language summary of a standard, as text read from its PDF.",
        },
        "summaries": dict(sorted(found.items())),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"looked up {len(wanted)} {counts}; {len(found)} summaries -> {SUMMARY_OUTPUT}")


# --- scopes: the scope clause of each standard published since the snapshot -----
#
# BIS's portal links each newly published standard to its document, free to
# read. Only its SCOPE clause is kept, read by the archive's own extractor
# (data/ingest_archive.py), and the document is not stored: the same use the
# archive copies are put to. Born-digital text, not OCR.

SCOPES = CACHE / "scopes"
SCOPE_OUTPUT = _REPO_ROOT / "data" / "bis_scopes.json"


def fetch_scope(item: dict, delay: float) -> str:
    path = SCOPES / (re.sub(r"[^A-Za-z0-9]+", "_", number_key(item["number"])).strip("_") + ".json")
    if path.exists():
        return "cached"
    from ingest_archive import clean_ocr, extract_scope
    import pymupdf
    try:
        request = urllib.request.Request(f"{OBJECT_STORE}/{item['document']}",
                                         headers={"User-Agent": HEADERS["User-Agent"]})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        with pymupdf.open(stream=data, filetype="pdf") as document:
            # The scope is on the first pages; reading them all costs only time
            # on a large standard.
            text = "\n".join(document[i].get_text() for i in range(min(len(document), 8)))
        scope = extract_scope(clean_ocr(text))
    except Exception as exc:  # noqa: BLE001 -- reported, retried on the next run
        return f"failed: {exc}"
    path.write_text(json.dumps({"number": item["number"], "scope": scope or ""}, ensure_ascii=False),
                    encoding="utf-8")
    time.sleep(delay)
    return "found" if scope else "none"


def scopes(workers: int, delay: float, limit: int) -> None:
    SCOPES.mkdir(parents=True, exist_ok=True)
    listed = json.loads(PUBLISHED.read_text(encoding="utf-8"))["standards"].values() if PUBLISHED.exists() else []
    wanted = [i for i in listed if i.get("document")]
    if limit:
        wanted = wanted[:limit]
    counts = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for i, future in enumerate(cf.as_completed([pool.submit(fetch_scope, item, delay) for item in wanted]), 1):
            status = future.result().split(":")[0]
            counts[status] = counts.get(status, 0) + 1
            if i % 100 == 0:
                print(f"{i}/{len(wanted)} {counts}", flush=True)
    found = {}
    for path in SCOPES.glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("scope"):
            found[record["number"]] = record["scope"]
    SCOPE_OUTPUT.write_text(json.dumps({
        "_meta": {"source": "SCOPE clause of each standard BIS published since 1 October 2025, read from the "
                            "document its standards portal links (" + PORTAL + ")",
                  "retrieved": date.today().isoformat(), "found": len(found)},
        "scopes": dict(sorted(found.items())),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(wanted)} documents {counts}; {len(found)} scopes -> {SCOPE_OUTPUT}")


# --- overlay: the portal's newer facts on the Know Your Standard record ---------

PORTAL_SOURCE_URL = PORTAL + "/website/know-your-standards"


def overlay(bis_raw: dict, portal: dict = None) -> dict:
    """Bring BIS's Know Your Standard record (number -> entry, as in
    bis_kys.json) up to date with the portal, in place. Returns counts.

    * an edition the portal shows withdrawn is withdrawn, with the date; a
      replacement named by the older record is kept
    * an amendment count the portal puts higher is taken, with the years
    * a standard published after the snapshot is added in the same shape, so
      the steps that read this record treat it like any other
    """
    if portal is None:
        if not OUTPUT.exists():
            return {}
        portal = json.loads(OUTPUT.read_text(encoding="utf-8"))
    by_key = {number_key(k): k for k in bis_raw}
    counts = {"withdrawn_since": 0, "amendments_since": 0, "published_since": 0}

    for number, rec in portal.get("standards", {}).items():
        key = by_key.get(number_key(number))
        if key is None:
            continue   # a published standard, handled below with its title
        entry = bis_raw[key]
        if rec.get("withdrawn") and not entry.get("withdrawn"):
            entry["withdrawn"] = True
            entry["withdrawn_on"] = rec.get("withdrawn_on")
            entry["status_from"] = "bis_portal"
            counts["withdrawn_since"] += 1
        if (rec.get("amendment_count") or 0) > (entry.get("amendment_count") or 0):
            entry["amendment_count"] = rec["amendment_count"]
            entry["amendments"] = rec.get("amendments", [])
            entry["amendments_from"] = "bis_portal"
            counts["amendments_since"] += 1

    for item in portal.get("published", []):
        if number_key(item["number"]) in by_key:
            continue
        rec = portal.get("standards", {}).get(item["number"], {})
        bis_raw[item["number"]] = {
            "number": item["number"],
            "title": item["title"],
            "withdrawn": bool(rec.get("withdrawn")),
            "withdrawn_on": rec.get("withdrawn_on"),
            "superseded_by": None,
            "revisions": "New Standard" if item.get("kind") == "new" else "Revised",
            "amendment_count": rec.get("amendment_count", 0),
            "amendments": rec.get("amendments", []),
            "reaffirmed": None,
            "qco_status": None,
            "remark": None,
            "page_id": None,
            "published_on": item.get("published_on"),
            "source_url": PORTAL_SOURCE_URL,
            "status_from": "bis_portal",
        }
        by_key[number_key(item["number"])] = item["number"]
        counts["published_since"] += 1
    return counts


# --- combine -------------------------------------------------------------------

def combine() -> None:
    standards = {}
    for path in sorted((CACHE / "details").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("found"):
            standards[record["number"]] = record
    pub = json.loads(PUBLISHED.read_text(encoding="utf-8")) if PUBLISHED.exists() else {"standards": {}}
    published_list = sorted(pub["standards"].values(), key=lambda s: (s["published_on"] or "", s["number"]))
    OUTPUT.write_text(json.dumps({
        "_meta": {
            "source": "BIS standards portal, " + PORTAL,
            "retrieved": date.today().isoformat(),
            "published_from": pub.get("from"),
            "published_to": pub.get("to"),
            "standards_checked": len(standards),
            "published": len(published_list),
            "note": ("BIS's current record per standard from its new portal: withdrawn and when, and "
                     "each amendment with its year. 'published' lists the standards BIS published or "
                     "revised in the date range, which its Know Your Standard pages do not hold."),
        },
        "published": published_list,
        "standards": standards,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    withdrawn = sum(1 for s in standards.values() if s.get("withdrawn"))
    amended = sum(1 for s in standards.values() if s.get("amendment_count"))
    print(f"standards {len(standards)}, withdrawn {withdrawn}, with amendments {amended}, "
          f"published {len(published_list)} -> {OUTPUT}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("published")
    p.add_argument("--from", dest="start", default=SNAPSHOT_END)
    p.add_argument("--to", dest="end", default=date.today().isoformat())
    p.add_argument("--delay", type=float, default=0.3)
    d = sub.add_parser("details")
    d.add_argument("--workers", type=int, default=3)
    d.add_argument("--delay", type=float, default=0.4)
    d.add_argument("--limit", type=int, default=0)
    d.add_argument("--only-amended", action="store_true",
                   help="skip editions BIS's older record shows as never amended")
    d.add_argument("--recheck-days", type=float, default=0,
                   help="fetch again any record cached more than this many days ago (withdrawals, new amendments)")
    sub.add_parser("combine")
    sc = sub.add_parser("scopes")
    sc.add_argument("--workers", type=int, default=2)
    sc.add_argument("--delay", type=float, default=0.5)
    sc.add_argument("--limit", type=int, default=0)
    m = sub.add_parser("summaries")
    m.add_argument("--workers", type=int, default=2)
    m.add_argument("--delay", type=float, default=0.4)
    m.add_argument("--limit", type=int, default=0, help="look up at most this many new standards (0: all)")
    args = ap.parse_args()
    if args.cmd == "published":
        published(args.start, args.end, args.delay)
    elif args.cmd == "details":
        details(args.workers, args.delay, args.limit, args.only_amended, args.recheck_days)
    elif args.cmd == "scopes":
        scopes(args.workers, args.delay, args.limit)
    elif args.cmd == "summaries":
        summaries(args.workers, args.delay, args.limit)
    else:
        combine()
    return 0


if __name__ == "__main__":
    sys.exit(main())
