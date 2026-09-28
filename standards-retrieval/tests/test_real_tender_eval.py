"""eval/real_tender_eval.py: turning tender lines that cite IS numbers into an answer key."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.real_tender_eval import as_query, base_number, cited, lines_with_citations  # noqa: E402

SOR = (
    "SECTION-I(IX): H.D.P.E. PIPES Sr. No. Description Unit "
    "1. Providing and supplying HDPE pipes PE 100, PN 10, for drinking water supply conforming to "
    "I.S. 4984/2016 including transport to site. Metre 540.00 "
    "2. Supplying and fixing C.I. manhole cover with frame, medium duty, conforming to IS: 1726 "
    "(latest revision). Each 3200.00 "
    "Notes: The design shall be in accordance with I.S. 456."
)


def test_each_item_line_becomes_a_query_and_its_answer():
    found = lines_with_citations(SOR)
    queries = [q for q, _ in found]
    assert any(q.startswith("Providing and supplying HDPE pipes PE 100") for q in queries)
    assert {"IS 4984"} in [labels for _, labels in found]
    assert {"IS 1726"} in [labels for _, labels in found]


def test_the_citation_is_taken_out_of_the_query():
    query = as_query("Supplying and fixing C.I. manhole cover, conforming to IS: 1726 (latest revision)")
    assert "1726" not in query and "IS" not in query.split()
    assert query.startswith("Supplying and fixing C.I. manhole cover")
    assert "1786" not in as_query("TMT bars Fe 500D as per I.S. 1786:2008, 12 mm")


def test_numbers_are_compared_without_edition_or_part():
    assert base_number("IS 694 (Part 2):2016") == "IS 694"
    assert base_number("IS/ISO 4427-2:2007") == "IS/ISO 4427"
    assert cited("conforming to I.S. 432 part-I or IS 1786 or IS/ISO 4427") == {"IS 432", "IS 1786", "IS/ISO 4427"}


def test_a_line_that_is_only_a_citation_is_skipped():
    assert lines_with_citations("Notes: IS 456.") == []
