"""Official amendment status from BIS's "Know Your Standard" pages.

BIS publishes a page per Indian Standard at

  https://www.services.bis.gov.in/php/BIS_2.0/bisconnect/knowyourstandards/Indian_standards/isdetails_mnd/<id>

giving the IS number, title, number of revisions, the number of amendments
("No amendment issued" or a count), the amendments themselves (number and
year), the reaffirmation year, whether it was withdrawn or superseded and by
what, and its QCO status. This is BIS's current record, so it replaces the
"at least N, from a copy current to <year>" answers read from archived texts.

The site notes that standards published after 1 October 2025 are on BIS's new
portal; for those this source has nothing and the archived text answer stands.

Pages are fetched politely (a pause between requests, a few in parallel at
most) and parsed as they arrive; each page's record is kept under
data/archive/kys_cache/<id>.json (not committed) so an interrupted run
resumes where it stopped. `combine` writes data/amendments/bis_kys.json.

Usage:
  python data/bis_kys.py fetch --start 1 --end 34300 [--workers 3] [--delay 0.4]
  python data/bis_kys.py combine
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

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from text_repair import fix_text  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE = _REPO_ROOT / "data" / "archive" / "kys_cache"
OUTPUT = _REPO_ROOT / "data" / "amendments" / "bis_kys.json"
URL = "https://www.services.bis.gov.in/php/BIS_2.0/bisconnect/knowyourstandards/Indian_standards/isdetails_mnd/{id}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StandEng standards research"


def fetch_one(page_id: int, delay: float) -> str:
    """Fetch and parse one page, keeping only the parsed record.

    A raw page is ~70 KB, so 34,000 of them would be ~2.4 GB; the parsed
    record is well under 1 KB. An empty page (no such id) is recorded too, so
    a resumed run does not fetch it again.
    """
    path = CACHE / f"{page_id}.json"
    if path.exists():
        return "cached"
    request = urllib.request.Request(URL.format(id=page_id), headers={"User-Agent": USER_AGENT})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                html = response.read().decode("utf-8", errors="replace")
            record = parse_page(html)
            path.write_text(json.dumps(record if record else {"empty": True}, ensure_ascii=False), encoding="utf-8")
            time.sleep(delay)
            return "fetched" if record else "empty"
        except Exception as exc:  # noqa: BLE001 -- retried, then reported
            time.sleep(2 * (attempt + 1))
            last = exc
    return f"failed: {last}"


def fetch(start: int, end: int, workers: int, delay: float) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    counts, started = {}, time.time()
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, i, delay): i for i in range(start, end + 1)}
        for n, future in enumerate(cf.as_completed(futures), 1):
            status = future.result().split(":")[0]
            counts[status] = counts.get(status, 0) + 1
            if n % 500 == 0:
                rate = n / (time.time() - started)
                print(f"{n}/{end - start + 1} {counts} {rate:.1f}/s", flush=True)
    print("done", counts, flush=True)


# --- parsing -------------------------------------------------------------------

_FIELD = re.compile(r"(IS Number|IS Title|Superseding IS|Superseded by IS|Degree of Equivalence|"
                    r"Number of Revisions|Number of Amendments|Aspect|Language|Reaffirmation Year|"
                    r"Technical Department|Technical Committee|QCO Status)\s*/[^:]*:\s*")


_NUMBER = re.compile(
    r"^((?:IS|SP|NBC)(?:/[A-Z]+)*\s*\d[\w\-.]*(?:\s*\([^)]*\))?(?:\s*:\s*(?:19|20)\d{2})?)\s*(.*)$"
)


def clean_number(raw: str):
    """The IS number, and whatever BIS wrote after it.

    'IS 3400 (Part 5):2020 ISO 36 : 2017' -> ('IS 3400 (Part 5):2020', 'ISO 36 : 2017')
    'IS 3175:2013 Decision taken to Reaffirm and Archive' -> ('IS 3175:2013', 'Decision ...')
    """
    raw = " ".join((raw or "").split())
    m = _NUMBER.match(raw)
    if not m:
        return raw, None
    number = re.sub(r"\s*:\s*", ":", m.group(1)).strip()
    return number, (m.group(2).strip() or None)


def parse_page(html: str):
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    start = text.find("Basic Details")
    if start < 0 or "IS Number" not in text[start:]:
        return None
    body = text[start:]
    fields, matches = {}, list(_FIELD.finditer(body))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else min(len(body), m.end() + 200)
        value = body[m.end():end].strip()
        fields.setdefault(m.group(1), value)
    number, remark = clean_number(fields.get("IS Number", "").split(" Comment")[0])
    if not number.startswith(("IS", "SP", "NBC")):
        return None

    amendments = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        head = [" ".join(c.get_text(" ", strip=True).split()).lower() for c in rows[0].find_all(["th", "td"])]
        if "amendment number" in head and "amendment year" in head:
            ni, yi = head.index("amendment number"), head.index("amendment year")
            for r in rows[1:]:
                cells = [" ".join(c.get_text(" ", strip=True).split()) for c in r.find_all(["td", "th"])]
                if len(cells) > max(ni, yi) and cells[ni]:
                    m = re.search(r"\d+", cells[ni])
                    y = re.search(r"(19|20)\d{2}", cells[yi])
                    amendments.append({"number": int(m.group(0)) if m else None,
                                       "label": cells[ni], "year": int(y.group(0)) if y else None})
            break

    stated = fields.get("Number of Amendments", "")
    count_match = re.match(r"(\d+)", stated)
    count = 0 if "no amendment" in stated.lower() else (int(count_match.group(1)) if count_match else None)
    superseded_by = fields.get("Superseded by IS")
    title = fields.get("IS Title", "")
    return {
        "number": number,
        "title": title,
        "withdrawn": "(withdrawn)" in title.lower(),
        "superseded_by": superseded_by.split(" Degree")[0] if superseded_by else None,
        "revisions": fields.get("Number of Revisions"),
        "amendment_count": count if count is not None else (len(amendments) or None),
        "amendments_stated": stated[:60],
        "amendments": amendments,
        "reaffirmed": (re.search(r"(19|20)\d{2}", fields.get("Reaffirmation Year", "") or "") or [None])[0],
        "qco_status": (fields.get("QCO Status") or "")[:80] or None,
        "remark": remark,
    }


def parse() -> None:
    """Combine the per-page records into data/amendments/bis_kys.json."""
    standards, empty = {}, 0
    files = sorted(CACHE.glob("*.json"), key=lambda p: int(p.stem))
    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("empty"):
            empty += 1
            continue
        # Records fetched before clean_number existed are cleaned here too.
        number, remark = clean_number(record["number"])
        record["number"], record["remark"] = number, record.get("remark") or remark
        # BIS stores some text double-encoded ("â€“" for an en dash).
        for field in ("title", "superseded_by", "remark"):
            record[field] = fix_text(record.get(field))
        record["page_id"] = int(path.stem)
        standards.setdefault(record["number"], record)
    OUTPUT.write_text(json.dumps({
        "_meta": {
            "source": URL.format(id="<id>"),
            "retrieved": date.today().isoformat(),
            "pages_read": len(files),
            "standards": len(standards),
            "empty_pages": empty,
            "note": "BIS's own record per standard. Standards published after 1 October 2025 are on BIS's new portal and not here.",
        },
        "standards": standards,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    with_amd = sum(1 for s in standards.values() if s["amendment_count"])
    print(f"pages {len(files)}, standards {len(standards)}, with amendments {with_amd}, empty {empty}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--start", type=int, default=1)
    f.add_argument("--end", type=int, default=34300)
    f.add_argument("--workers", type=int, default=3)
    f.add_argument("--delay", type=float, default=0.4)
    sub.add_parser("combine")
    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch(args.start, args.end, args.workers, args.delay)
    else:
        parse()


if __name__ == "__main__":
    sys.exit(main())
