"""BIS's new standards portal, overlaid on the Know Your Standard record, and
the scope clause read where its heading runs into the text."""

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "data"))
sys.path.insert(0, str(_REPO / "standards-retrieval"))

import amendments  # noqa: E402
from bis_portal import _amendment_number, number_key, overlay, tidy_number  # noqa: E402
from ingest_archive import extract_scope  # noqa: E402


def kys(number, **fields):
    return {"number": number, "title": "A title", "withdrawn": False, "superseded_by": None,
            "amendment_count": 0, "amendments": [], "page_id": 1, **fields}


class TestNumbers:
    def test_spellings_compare_equal(self):
        assert number_key("IS 1239 ( Part 1 ) : 2004") == number_key("IS 1239 (PART 1):2004")
        assert number_key("IS\\/ISO 4427-2:2007") == number_key("IS/ISO 4427-2:2007")

    def test_bis_capitals_take_the_corpus_spelling(self):
        assert tidy_number("IS 101 (PART 1/SEC 2):2023") == "IS 101 (Part 1/Sec 2):2023"

    def test_amendment_numbers_come_from_the_label(self):
        assert _amendment_number("Sixth Amendment", 9) == 6
        assert _amendment_number("Amendment No. 3", 9) == 3
        assert _amendment_number("", 4) == 4


class TestOverlay:
    def test_a_withdrawal_since_the_snapshot_is_applied_with_its_date(self):
        record = {"IS 4246:2002": kys("IS 4246:2002", superseded_by="IS 4246:2025")}
        counts = overlay(record, {"standards": {"IS 4246:2002": {
            "found": True, "withdrawn": True, "withdrawn_on": "2026-06-23"}}, "published": []})
        assert counts["withdrawn_since"] == 1
        assert record["IS 4246:2002"]["withdrawn"] is True
        assert record["IS 4246:2002"]["withdrawn_on"] == "2026-06-23"
        # The replacement the older record named is kept.
        assert record["IS 4246:2002"]["superseded_by"] == "IS 4246:2025"

    def test_a_higher_amendment_count_is_taken_and_a_lower_one_is_not(self):
        record = {"IS 1:2000": kys("IS 1:2000", amendment_count=2),
                  "IS 2:2000": kys("IS 2:2000", amendment_count=3)}
        later = [{"number": n, "label": "", "year": 2020 + n} for n in (1, 2, 3)]
        overlay(record, {"standards": {
            "IS 1:2000": {"found": True, "amendment_count": 3, "amendments": later},
            "IS 2:2000": {"found": True, "amendment_count": 1, "amendments": later[:1]},
        }, "published": []})
        assert record["IS 1:2000"]["amendment_count"] == 3
        assert record["IS 1:2000"]["amendments"] == later
        assert record["IS 2:2000"]["amendment_count"] == 3

    def test_a_standard_published_since_is_added_in_the_same_shape(self):
        record = {}
        overlay(record, {"standards": {}, "published": [{
            "number": "IS 19609:2026", "title": "uPVC profiles framed doors - Specification",
            "published_on": "2026-08-28", "kind": "new"}]})
        entry = record["IS 19609:2026"]
        assert entry["withdrawn"] is False and entry["status_from"] == "bis_portal"
        assert entry["published_on"] == "2026-08-28" and entry["page_id"] is None

    def test_a_published_standard_already_held_is_not_added_twice(self):
        record = {"IS 1946:2026": kys("IS 1946:2026")}
        counts = overlay(record, {"standards": {}, "published": [{
            "number": "IS 1946 : 2026", "title": "Fixing devices", "published_on": "2026-09-15", "kind": "revised"}]})
        assert counts["published_since"] == 0 and len(record) == 1


class TestAmendmentLayer:
    def test_the_portal_fills_years_and_newer_amendments(self):
        merged = amendments._with_portal(
            {"amendment_count": 1, "amendments": [], "withdrawn": False},
            {"amendment_count": 2, "amendments": [{"number": 1, "year": 2013}, {"number": 2, "year": 2026}]})
        assert merged["amendment_count"] == 2 and merged["from_portal"]
        result = amendments._official("IS 9:2000", merged, None, None)
        assert result["count"] == 2
        assert [a["date"] for a in result["amendments"]] == ["2013", "2026"]
        assert "standards portal" in result["note"]

    def test_without_a_portal_record_the_snapshot_stands(self):
        record = {"amendment_count": 1, "amendments": []}
        assert amendments._with_portal(record, None) is record


class TestScopeClause:
    def test_an_inline_heading_beats_a_foreword_sentence(self):
        text = ("FOREWORD This standard specifies the acceptable limits and the permissible limits in the "
                "absence of alternate source. 1 SCOPE This standard prescribes the requirements and the "
                "methods of sampling and test for drinking water. 2 REFERENCES The standards listed in Annex A.")
        assert extract_scope(text) == ("This standard prescribes the requirements and the methods of "
                                       "sampling and test for drinking water.")

    def test_a_later_clause_named_scope_is_not_taken(self):
        text = ("Foreword text with nothing to take. 3.1 Scope The specimen shall be prepared and mounted "
                "in accordance with the detail specification and tested. 4 PROCEDURE Apply the load.")
        assert extract_scope(text) is None


class TestTitles:
    def test_amendment_notes_are_not_part_of_the_title(self):
        from apply_bis_status import clean_bis_title
        assert clean_bis_title("Pressed Ceramic Tiles - Specification Amendment - 2") == \
            "Pressed Ceramic Tiles - Specification"
        assert clean_bis_title("Amendment No. 2 to IS 18297: 2023 Cabinet Hinges — Specification") == \
            "Cabinet Hinges — Specification"
        assert clean_bis_title("IS 303: 2024 Plywood for General Purposes - Specification ( Draft Second Amendme") == \
            "Plywood for General Purposes - Specification"
        assert clean_bis_title("Valves of Automotive Air Brake Systems - Method of Test (Amendment-1)") == \
            "Valves of Automotive Air Brake Systems - Method of Test"

    def test_a_title_about_an_amendment_is_kept(self):
        from apply_bis_status import clean_bis_title
        assert clean_bis_title("Agriculture Grade Iron Pyrites as Soil Amendment") == \
            "Agriculture Grade Iron Pyrites as Soil Amendment"


class TestNewEditions:
    def test_a_new_edition_is_searched_with_the_scope_of_the_one_it_revises(self):
        from add_bis_standards import additions
        held = [{"id": "IS-GEN-0001", "number": "IS 1299:1984", "title": "Dimensional changes on washing",
                 "scope": "This standard prescribes a method for determination of dimensional changes.",
                 "provenance": "published_text_ocr", "status": "active"}]
        bis = {"IS 1299:2026": kys("IS 1299:2026", title="Dimensional changes on washing - Method"),
               "IS 19609:2026": kys("IS 19609:2026", title="uPVC profiles framed doors - Specification")}
        added, _ = additions(held, bis)
        by_number = {r["number"]: r for r in added}
        revision = by_number["IS 1299:2026"]
        assert revision["scope"] == held[0]["scope"]
        assert revision["provenance"] == "scope_from_previous_edition"
        assert revision["scope_edition"] == "IS 1299:1984"
        # A standard with no earlier edition has no scope to borrow.
        new = by_number["IS 19609:2026"]
        assert new["scope"] == "" and new["provenance"] == "number_and_title_only"
