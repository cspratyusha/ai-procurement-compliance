"""Parse BIS's published lists of products under compulsory certification.

Source pages (saved HTML, passed on the command line):

  ISI  Scheme I, ISI mark          https://www.bis.gov.in/product-certification/products-under-compulsory-certification/scheme-i-mark-scheme/
  CRS  Scheme II, registration     https://www.bis.gov.in/product-certification/products-under-compulsory-certification/scheme-ii-registration-scheme/
  X    Scheme X, certification     https://www.bis.gov.in/products-under-compulsory-certification-scheme-x/

Each page holds one or more HTML tables with an IS number column, a product
column and a notification column (the Quality Control Order and its gazette
S.O. number). The notification cell spans every row it covers with rowspan,
and category headings are rows with one cell spanning the table; both are
resolved here, so every output row carries its own order.

A row whose notification is a deferment is recorded with status "deferred":
the product is named in an order, but the phase covering it is not yet in
force, so it must not be reported as mandatory.

IS numbers are rewritten in the corpus's spelling: 'IS/IEC 60947 : Part 4 :
Sec 1 : 2018' becomes 'IS/IEC 60947-4-1:2018', 'IS 302-2-25' becomes
'IS 302 (Part 2/Sec 25)'. Matching to corpus editions is certification.py's job.

Output: data/certification/bis_compulsory.json

The pages as read, and the deferment order, are kept in data/certification/source/.

Usage:
  python data/certification/parse_bis_compulsory.py --fetch      # read BIS's pages now
  python data/certification/parse_bis_compulsory.py \\
      --scheme ISI data/certification/source/bis_scheme_i.html \\
      --scheme CRS data/certification/source/bis_scheme_ii_crs.html \\
      --scheme X   data/certification/source/bis_scheme_x.html

--fetch downloads the English pages (BIS serves the Hindi page by default,
whose column headings this parser does not read: a plain download parsed to
nothing) into source/, and keeps the previous list if a scheme parses to no
rows or the total falls by more than a tenth, since that is a page that
changed shape, not BIS lifting a tenth of its orders overnight. The engine's
refresh runs it (standards-retrieval/bis_refresh.py).
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

OUT = Path(__file__).resolve().parent / "bis_compulsory.json"
SOURCE_DIR = Path(__file__).resolve().parent / "source"
SOURCE_FILES = {"ISI": "bis_scheme_i.html", "CRS": "bis_scheme_ii_crs.html", "X": "bis_scheme_x.html"}
MAX_DROP = 0.10

SOURCES = {
    "ISI": "https://www.bis.gov.in/product-certification/products-under-compulsory-certification/scheme-i-mark-scheme/",
    "CRS": "https://www.bis.gov.in/product-certification/products-under-compulsory-certification/scheme-ii-registration-scheme/",
    "X": "https://www.bis.gov.in/products-under-compulsory-certification-scheme-x/",
}

_IS_START = re.compile(r"\bIS(?![A-Za-z])\s*(?:/\s*(IEC|ISO))?", re.IGNORECASE)
# International numbers quoted alongside the Indian one: "(ISO 683-17: 2014)",
# "/ISO 606 : 2004", "IEC 60335-1:2020". Removed before reading the IS number.
_FOREIGN = re.compile(
    r"\(\s*(?:ISO|IEC|EN)\b[^)]*\)"
    # A foreign number standing alone or after a slash ("2019/ISO 19062-1 : 2015"),
    # but not the second half of an adopted number ("IS/ISO 11951").
    r"|(?<!IS/)(?<!IS /)(?<![A-Za-z])(?:ISO|IEC|EN)\s*\d[\d\s\-:.]*",
    re.IGNORECASE,
)
_SO = re.compile(r"S\.?\s*O\.?\s*(?:No\.?)?\s*\d+\s*\(\s*E\s*\)[^;]*?\d{4}", re.IGNORECASE)
_DEFERRED = re.compile(r"\bdefer", re.IGNORECASE)

# Scheme X is the Electrical Equipment (Quality Control) Order, 2020. S.O.
# 5038(E) of 6 November 2025 defers "the date of enforcement for all product
# categories specified in the Table to the said Order except those mentioned
# at Sr. No. 1.1(a), which have already been implemented on the 10th November,
# 2024 ... until further orders". The per-row notification text on the BIS
# page is not reliable for this (some rows still cite the earlier S.O.
# 2007(E) timeline), so the order itself decides.
SCHEME_X_IN_FORCE = {"1.1(a)"}
SCHEME_X_DEFERMENT = {
    "order": "S.O. 5038(E) dated 6 November 2025 (Ministry of Heavy Industries)",
    "url": "https://www.bis.gov.in/wp-content/uploads/2025/11/Deferment-of-upcoming-phase-implementation-of-the-Electrical-Equipment-Quality-Control-Order-2020.pdf",
    "text": "Enforcement deferred until further orders; only Sr. No. 1.1(a) has been in force since 10 November 2024.",
}


def clean(text: str) -> str:
    return " ".join((text or "").replace("–", "-").replace("—", "-").split())


def grid(table):
    """Rows as lists of cells, with rowspan cells repeated into the rows they cover."""
    carried = {}
    out = []
    for tr in table.find_all("tr"):
        queue = list(tr.find_all(["td", "th"]))
        row, col = [], 0
        while queue or col in carried:
            if col in carried:
                cell, left = carried[col]
                row.append(cell)
                if left <= 1:
                    del carried[col]
                else:
                    carried[col] = (cell, left - 1)
                col += 1
                continue
            cell = queue.pop(0)
            span = int(cell.get("colspan") or 1)
            rows = int(cell.get("rowspan") or 1)
            for i in range(span):
                row.append(cell)
                if rows > 1:
                    carried[col + i] = (cell, rows - 1)
            col += span
        out.append(row)
    return out


def _format(prefix, base, parts, year):
    if prefix:                                    # IS/IEC 60947-4-1:2018
        number = f"IS/{prefix.upper()} {base}" + "".join(f"-{p}" for p in parts)
    else:                                         # IS 302 (Part 2/Sec 25):2009
        number = f"IS {base}"
        if parts:
            inner = f"Part {parts[0]}" + "".join(f"/Sec {p}" for p in parts[1:])
            number += f" ({inner})"
    return number + (f":{year}" if year else "")


def numbers_in(text: str):
    """Every IS number in a cell, in corpus spelling."""
    text = _FOREIGN.sub(" ", clean(text))
    starts = list(_IS_START.finditer(text))
    found = []
    for i, m in enumerate(starts):
        chunk = text[m.end(): starts[i + 1].start() if i + 1 < len(starts) else len(text)]
        base = re.match(r"\s*[:\-]?\s*(\d{1,5})", chunk)
        if not base:
            continue
        rest = chunk[base.end():]
        year = None
        ym = re.search(r":\s*((?:19|20)\d{2})\b(?!.*:\s*(?:19|20)\d{2}\b)", rest)
        if ym:
            year = ym.group(1)
            rest = rest[:ym.start()] + rest[ym.end():]
        parts = re.findall(r"(?:part|sec(?:tion)?)\s*\.?\s*-?\s*(\d+[A-Za-z]?)", rest, re.IGNORECASE)
        if not parts:
            # Dash form: IS 302-2-25, IS/IEC 61730-1, and BIS's own "IS 302-2:26".
            dash = re.match(r"(\s*-\s*\d+[A-Za-z]?(?:\s*[-:]\s*\d{1,3}[A-Za-z]?(?!\d))*)", rest)
            if dash:
                parts = re.findall(r"\d+[A-Za-z]?", dash.group(1))
        found.append(_format(m.group(1), base.group(1), parts, year))
    return list(dict.fromkeys(found))


def _columns(header):
    """Indexes of the IS number, product, title and notification columns."""
    names = [clean(c.get_text(" ", strip=True)).lower() for c in header]
    def find(*keys):
        for key in keys:
            for i, n in enumerate(names):
                if key in n:
                    return i
        return None
    return {
        "is": find("is no", "is number", "indian standard"),
        "product": find("product category", "product"),
        "title": find("title"),
        "notice": find("notification", "details"),
    }


def parse(path: Path, scheme: str):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    entries = []
    for table in soup.find_all("table"):
        rows = grid(table)
        if not rows:
            continue
        cols = _columns(rows[0])
        if cols["is"] is None or cols["product"] is None:
            continue
        if cols["notice"] is None:
            cols["notice"] = len(rows[0]) - 1
        category = None
        table_order = None          # the first order the table cites, for rows BIS left blank
        for row in rows[1:]:
            if len({id(c) for c in row}) == 1:           # a heading spanning the table
                category = clean(row[0].get_text(" ", strip=True)).rstrip(" :")
                continue
            # A row with a missing cell (BIS leaves some out) still has its IS
            # number first and its notification last; take the title as the
            # product when the product column is not there.
            def text(k):
                i = cols[k] if k != "notice" else (cols[k] if len(row) > cols[k] else len(row) - 1)
                return clean(row[i].get_text(" ", strip=True)) if i is not None and i < len(row) else ""
            is_text = text("is")
            product = text("product") if len(row) > cols["notice"] else ""
            product = product or text("title")
            numbers = numbers_in(is_text)
            if not numbers or not product:
                continue
            notice_cell = row[cols["notice"]] if len(row) > cols["notice"] else row[-1]
            notice = clean(notice_cell.get_text(" ", strip=True))
            link = notice_cell.find("a")
            qco = re.split(r"\s+S\.?\s*O\.?\s*(?:No\.?)?\s*\d", notice, maxsplit=1)[0]
            qco = re.sub(r"^\d+\.\s*", "", qco).strip(" ,([")
            so = _SO.search(notice)
            if qco.upper().startswith(("SO ", "S.O", "S O")):
                qco = ""                            # the cell opens with the gazette number
            if not qco and so:
                qco = f"Order notified by {clean(so.group(0))}"
            from_table = False
            if not notice and table_order:
                # Blank notification cell: the row sits in a table under one
                # order (e.g. the Electronics and IT Goods CRS order), so it is
                # attributed to that order and flagged as such.
                qco, url, so_text, from_table = table_order["qco"], table_order["url"], table_order["gazette"], True
            else:
                url, so_text = (link.get("href") if link else None), (clean(so.group(0)) if so else None)
            if qco and not from_table and table_order is None:
                table_order = {"qco": qco, "url": url, "gazette": so_text}
            sr = re.sub(r"\s+", "", clean(row[0].get_text(" ", strip=True))).rstrip(".")
            if scheme == "X":
                status = "in_force" if sr in SCHEME_X_IN_FORCE else "deferred"
            else:
                status = "deferred" if _DEFERRED.search(notice) else "in_force"
            for number in numbers:
                entries.append({
                    "is_number": number,
                    "is_cell": is_text,
                    "sr": sr or None,
                    "product": product,
                    "title": text("title") or None,
                    "scheme": scheme,
                    "status": status,
                    "deferment": SCHEME_X_DEFERMENT if status == "deferred" and scheme == "X" else None,
                    "category": category,
                    "qco": qco or None,
                    "gazette": so_text,
                    "qco_url": url,
                    "order_from_table": from_table,
                    "source": SOURCES[scheme],
                })
    return entries


def fetch() -> list:
    """Download the English pages to temporary files; [(scheme, path)]."""
    import urllib.request

    fetched = []
    for scheme, url in SOURCES.items():
        request = urllib.request.Request(url + "?lang=en", headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StandEng standards research",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(request, timeout=120) as response:
            html = response.read()
        path = SOURCE_DIR / (SOURCE_FILES[scheme] + ".new")
        path.write_bytes(html)
        fetched.append((scheme, path))
    return fetched


def _discard(sources) -> None:
    for _, path in sources:
        if path.suffix == ".new":
            path.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", action="append", nargs=2, metavar=("SCHEME", "HTML"))
    ap.add_argument("--fetch", action="store_true", help="download BIS's pages now and parse them")
    args = ap.parse_args()
    if not args.fetch and not args.scheme:
        ap.error("give --fetch or --scheme")

    sources = fetch() if args.fetch else [(s, Path(h)) for s, h in args.scheme]
    entries = []
    for scheme, html in sources:
        got = parse(Path(html), scheme.upper())
        print(f"{scheme}: {len(got)} rows from {html}")
        if args.fetch and not got:
            print(f"KEPT the previous list: {scheme} parsed to no rows, so its page has changed shape")
            _discard(sources)
            return 0
        entries += got

    seen, unique = set(), []
    for e in entries:
        key = (e["scheme"], e["is_number"], e["product"].lower(), e["status"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    if args.fetch and OUT.exists():
        before = len(json.loads(OUT.read_text(encoding="utf-8"))["entries"])
        if len(unique) < before * (1 - MAX_DROP):
            print(f"KEPT the previous list: {len(unique)} entries against {before} before")
            _discard(sources)
            return 0
        added = len(unique) - before
        for scheme, path in sources:
            path.replace(SOURCE_DIR / SOURCE_FILES[scheme])     # the pages as read, kept
        print(f"{'+' if added >= 0 else ''}{added} entries since the last read")

    payload = {
        "_meta": {
            "description": "Products under BIS compulsory certification, as published by BIS.",
            "sources": {s.upper(): SOURCES[s.upper()] for s, _ in sources},
            "retrieved": date.today().isoformat(),
            "note": (
                "Rows as BIS lists them, IS numbers rewritten in corpus spelling. status "
                "'deferred' means the order names the product but the phase covering it is "
                "not yet in force."
            ),
        },
        "entries": unique,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(unique)} entries to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
