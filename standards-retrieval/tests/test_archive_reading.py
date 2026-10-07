"""Reading the archived texts: sectors, citations, and texts filed under the wrong number."""

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "data"))

import extract_references as refs  # noqa: E402
import ingest_archive  # noqa: E402

SOURCE = {"family": "IS 1811", "number": "IS 1811:1984"}


def cited(text, source=SOURCE):
    return sorted(refs.extract(source, text, {}).keys())


class TestCitations:
    def test_a_real_citation_is_read(self):
        assert cited("conforming to IS 2062 and IS 1786.") == ["IS 1786", "IS 2062"]

    def test_its_own_number_with_the_next_clause_run_in_is_not_a_citation(self):
        # "IS : 1811 3. SAMPLING" OCR'd without the space reads as IS 18113.
        assert cited("as specified. 4 IS : 18113. SAMPLING BEDS 3.1 While") == []

    def test_a_number_broken_by_an_apostrophe_is_not_read(self):
        # "IS 365'7" is IS 3657 with OCR noise, not IS 365.
        assert cited("any one of the IQIs described in IS 365'7 may be used") == []

    def test_other_bodies_numbers_in_a_references_block_are_not_read(self):
        block = ("2 REFERENCES The following Indian Standards are necessary adjuncts: "
                 "IS No. Title 2062 : 2011 Hot rolled steel ISO/DIS 14682 : 1996 Side guards "
                 "CISPR 22 : 2005 Information technology equipment ASTM D3418 : 2015 Transition "
                 "temperatures IEC/TR 61000 : 2002 Compatibility given 456 : 2000 Concrete "
                 "equipIS0 8058 : 1985 Air cargo ISIISO 9001 : 1994 Quality prEN 1904 : 1995 Solders "
                 "residential buildings of Workmen 3861 : 1975 Plinth area slabs 6126 : 1971 Nitro")
        assert cited(block) == ["IS 2062", "IS 3861", "IS 456", "IS 6126"]


class TestSectors:
    def test_the_sector_rules_carry_word_boundaries_not_control_characters(self):
        # A "\b" turned into a backspace by an edit made 9 sectors unmatchable
        # from 26 September to 5 October (metals: 4 records, automotive: 0).
        # The same slip recurred in extract_references.py on 6 October.
        for name in ("ingest_archive.py", "extract_references.py"):
            source = (_REPO / "data" / name).read_text(encoding="utf-8")
            assert "\x08" not in source, name

    def test_each_sector_is_reachable(self):
        for title, sector in [("Aluminium alloy ingots", "metals_alloys"),
                              ("Bitumen emulsion for roads", "petroleum_lubricants"),
                              ("Paper for printing", "paper_printing"),
                              ("Automotive vehicles brake linings", "automotive"),
                              ("Lacquer for metal", "paints_coatings")]:
            assert ingest_archive.classify(title, "") == sector, title


class TestMisfiled:
    def test_listed_texts_are_another_document(self):
        listed = json.loads((_REPO / "data" / "archive" / "misfiled.json").read_text(encoding="utf-8"))["misfiled"]
        assert "gov.in.is.62.2006" in listed and "SP 62" in listed["gov.in.is.62.2006"]
        assert ingest_archive.misfiled() == set(listed)
