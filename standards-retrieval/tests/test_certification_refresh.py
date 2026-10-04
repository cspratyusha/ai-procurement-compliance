"""Reading BIS's compulsory-certification pages again must never empty the list."""

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "data" / "certification"))

import parse_bis_compulsory as cert  # noqa: E402

SOURCE = _REPO / "data" / "certification" / "source"


def setup(tmp_path, monkeypatch, pages):
    """A copy of the current list, and `fetch` returning the given pages."""
    out = tmp_path / "bis_compulsory.json"
    out.write_text((_REPO / "data" / "certification" / "bis_compulsory.json").read_text(encoding="utf-8"),
                   encoding="utf-8")
    monkeypatch.setattr(cert, "OUT", out)
    monkeypatch.setattr(cert, "SOURCE_DIR", tmp_path)
    fetched = []
    for scheme, html in pages.items():
        path = tmp_path / (cert.SOURCE_FILES[scheme] + ".new")
        path.write_text(html, encoding="utf-8")
        fetched.append((scheme, path))
    monkeypatch.setattr(cert, "fetch", lambda: fetched)
    monkeypatch.setattr(sys, "argv", ["parse_bis_compulsory.py", "--fetch"])
    return out, json.loads(out.read_text(encoding="utf-8"))["entries"]


def saved(scheme):
    return (SOURCE / cert.SOURCE_FILES[scheme]).read_text(encoding="utf-8")


def test_the_pages_as_read_rebuild_the_same_list(tmp_path, monkeypatch):
    out, before = setup(tmp_path, monkeypatch, {s: saved(s) for s in ("ISI", "CRS", "X")})
    assert cert.main() == 0
    assert json.loads(out.read_text(encoding="utf-8"))["entries"] == before


def test_a_page_that_parses_to_nothing_leaves_the_list_alone(tmp_path, monkeypatch):
    # BIS's Hindi page, or any redesign: no table the parser recognises.
    pages = {"ISI": "<html lang='hi-IN'><table><tr><td>मानक</td></tr></table></html>",
             "CRS": saved("CRS"), "X": saved("X")}
    out, before = setup(tmp_path, monkeypatch, pages)
    assert cert.main() == 0
    assert json.loads(out.read_text(encoding="utf-8"))["entries"] == before
    assert not list(tmp_path.glob("*.new")), "the pages that were not used are not kept"
