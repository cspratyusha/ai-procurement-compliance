"""Tests for published-amendment data.

An amendment can change the material, the test regime or the acceptance
criteria, so a tender citing an un-amended edition can specify something that
is no longer conformant. The tests here are mostly about not overstating what
we know: a count without dates must not become invented dates, and an
unresearched standard must not read as having no amendments.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import amendments  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class _WithoutBIS(unittest.TestCase):
    """Tests of the researched and text layers, with BIS's record switched off.

    BIS's record takes priority when present; these pin the layers beneath it,
    which still answer for every standard BIS has no page for.
    """

    @classmethod
    def setUpClass(cls):
        cls._saved = amendments._BIS_PATH
        amendments._BIS_PATH = cls._saved.with_name("no-such-file.json")
        amendments.reset_cache()

    @classmethod
    def tearDownClass(cls):
        amendments._BIS_PATH = cls._saved
        amendments.reset_cache()


class TestAmendments(_WithoutBIS):
    def test_known_standard_lists_its_amendments(self):
        result = amendments.for_standard("IS 456:2000")
        self.assertTrue(result["checked"])
        self.assertEqual(result["count"], 6)
        self.assertEqual(len(result["amendments"]), 6)

        fourth = next(a for a in result["amendments"] if a["number"] == 4)
        self.assertEqual(fourth["readable_date"], "May 2013")
        self.assertEqual(fourth["confidence"], "confirmed")
        self.assertIn("aggregates", fourth["summary"].lower())

    def test_count_without_dates_does_not_invent_them(self):
        """BIS states IS 694 has four amendments but not which or when.

        Listing four entries with plausible-looking dates would be fabrication.
        The count is reported; the list stays empty.
        """
        result = amendments.for_standard("IS 694:2010")
        self.assertTrue(result["checked"])
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["amendments"], [])
        self.assertIn("4 published amendments", result["citation"])

    def test_standard_with_no_text_is_reported_as_unchecked(self):
        """Not the same as having no amendments."""
        result = amendments.for_standard("IS 99999:2020")
        self.assertEqual(result["status"], "unchecked")
        self.assertFalse(result["checked"])
        self.assertIsNone(result["count"])
        self.assertEqual(result["citation"], "IS 99999:2020")
        self.assertIn("not been checked", result["note"])

    def test_citation_names_the_latest_amendment_when_known(self):
        citation = amendments.for_standard("IS 456:2000")["citation"]
        self.assertIn("IS 456:2000", citation)
        self.assertIn("all 6 amendments", citation)
        self.assertIn("Amendment No. 6", citation)
        self.assertIn("June 2024", citation)

    def test_citation_omits_an_unknown_date(self):
        """IS 800 amendment 2 has no published date in our sources."""
        result = amendments.for_standard("IS 800:2007")
        second = next(a for a in result["amendments"] if a["number"] == 2)
        self.assertIsNone(second["readable_date"])
        self.assertNotIn("None", result["citation"])

    def test_is_number_spellings_resolve(self):
        canonical = amendments.for_standard("IS 456:2000")
        for spelling in ("is 456:2000", "IS 456 : 2000"):
            with self.subTest(spelling=spelling):
                self.assertEqual(
                    amendments.for_standard(spelling)["count"], canonical["count"]
                )

    def test_every_entry_is_for_a_standard_in_the_corpus(self):
        corpus = {
            s["number"]
            for s in json.loads(
                (_REPO_ROOT / "data" / "standards_corpus.json").read_text(encoding="utf-8")
            )
        }
        payload = json.loads(
            (_REPO_ROOT / "data" / "amendments" / "amendments.json").read_text(encoding="utf-8")
        )
        for number in payload["standards"]:
            with self.subTest(number=number):
                self.assertIn(number, corpus)

    def test_every_amendment_declares_its_confidence(self):
        """A 'likely' date read from a secondary source must say so."""
        payload = json.loads(
            (_REPO_ROOT / "data" / "amendments" / "amendments.json").read_text(encoding="utf-8")
        )
        for number, entry in payload["standards"].items():
            for item in entry.get("amendments", []):
                with self.subTest(number=number, amendment=item["number"]):
                    self.assertIn(item.get("confidence"), {"confirmed", "likely"})


class TestReadFromText(_WithoutBIS):
    """Amendments read from the slips bound into each standard's archived copy."""

    def test_researched_entries_win_over_text(self):
        """IS 456's copy (current to 2007) holds 2 slips; the researched 6 stand."""
        result = amendments.for_standard("IS 456:2000")
        self.assertEqual(result["status"], "researched")
        self.assertEqual(result["count"], 6)

    def test_slips_are_read_with_their_dates(self):
        """IS 1537 carries slips 1, 2, 4 and 5; 3 is known only because 4 exists."""
        result = amendments.for_standard("IS 1537:1976")
        self.assertEqual(result["status"], "found_in_text")
        self.assertEqual(result["count"], 5)
        by_number = {a["number"]: a for a in result["amendments"]}
        self.assertEqual(by_number[1]["readable_date"], "July 1977")
        self.assertEqual(by_number[3]["confidence"], "implied")
        self.assertIsNone(by_number[3]["date"])           # never invented
        self.assertIn("any later amendments", result["citation"])
        self.assertIn("Amendment No. 5 (May 1994)", result["citation"])

    def test_text_answers_say_how_recent_the_copy_is(self):
        result = amendments.for_standard("IS 1537:1976")
        self.assertTrue(result["copy_as_of"])
        self.assertIn(str(result["copy_as_of"]), result["note"])
        self.assertIn("Later amendments may exist", result["note"])

    def test_a_copy_without_slips_is_not_no_amendments(self):
        data = json.loads((_REPO_ROOT / "data" / "amendments" / "extracted_amendments.json").read_text(encoding="utf-8"))
        number = next(n for n, v in data["standards"].items() if v["count_in_copy"] == 0)
        result = amendments.for_standard(number)
        self.assertEqual(result["status"], "none_in_copy")
        self.assertFalse(result["checked"])
        self.assertIsNone(result["count"])
        self.assertIn("confirm with BIS", result["note"])

    def test_coverage_counts_both_sources(self):
        c = amendments.coverage()
        self.assertGreater(c["standards_with_amendments"], 3000)
        self.assertGreater(c["standards_checked"], 20000)
        self.assertGreaterEqual(c["standards_with_amendments"], c["standards_researched"])


class TestOfficialRecord(unittest.TestCase):
    """BIS's own record for each standard: the current count, which wins."""

    @classmethod
    def setUpClass(cls):
        path = _REPO_ROOT / "data" / "amendments" / "bis_kys.json"
        if not path.exists():
            raise unittest.SkipTest("BIS record not fetched")
        cls.records = json.loads(path.read_text(encoding="utf-8"))["standards"]
        amendments.reset_cache()

    def _one(self, predicate):
        for number, record in self.records.items():
            if predicate(record):
                return number, record
        self.skipTest("no such record in the data")

    def test_the_official_count_is_used(self):
        number, record = self._one(lambda r: (r.get("amendment_count") or 0) >= 2)
        info = amendments.for_standard(number)
        self.assertEqual(info["status"], "official")
        self.assertGreaterEqual(info["count"], record["amendment_count"])
        self.assertIn("according to BIS", info["note"])
        self.assertEqual([a["number"] for a in info["amendments"]], list(range(1, info["count"] + 1)))

    def test_no_amendment_issued_is_a_definite_answer(self):
        number, _ = self._one(lambda r: r.get("amendment_count") == 0)
        info = amendments.for_standard(number)
        if info["count_confidence"] == "disputed":
            self.skipTest("the archived copy disagrees for this one")
        self.assertEqual((info["status"], info["count"]), ("official", 0))
        self.assertIn("No amendment issued", info["note"])
        self.assertEqual(info["citation"], number)

    def test_a_disagreement_with_the_archived_copy_is_stated(self):
        amendments._load()
        disputed = next((k for k, v in amendments._BIS.items()
                         if v.get("amendment_count") == 0 and (amendments._EXTRACTED.get(k) or {}).get("count_in_copy")), None)
        if disputed is None:
            self.skipTest("no disagreement in the data")
        info = amendments.for_standard(disputed)
        self.assertEqual(info["count_confidence"], "disputed")
        self.assertIn("confirm with BIS", info["note"])
        self.assertGreater(info["count"], 0)         # the slip is not thrown away


class TestExtractor(unittest.TestCase):
    """The slip reader in data/extract_amendments.py, on known header shapes."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(_REPO_ROOT / "data"))
        import extract_amendments
        cls.read = staticmethod(extract_amendments.read)

    def test_a_clean_slip(self):
        text = ("AMENDMENT NO. 1 AUGUST 1991 TO IS 10 ( Part 4 ) : 1989 PLYWOOD TEA-CHESTS "
                "( Page 1, clause 4.1, line 1 ) - Delete the word 'nominal'. Reprography Unit, BIS")
        result = self.read("IS 10 (Part 4):1989", 1989, text)
        self.assertEqual(result["count_in_copy"], 1)
        self.assertEqual(result["amendments"][0]["date"], "1991-08")
        self.assertIn("clause 4.1", result["amendments"][0]["excerpt"])

    def test_a_slip_for_another_standard_is_ignored(self):
        text = "AMENDMENT NO. 2 MAY 1995 TO IS 4031 : 1988 METHODS OF PHYSICAL TESTS ( Page 3 )"
        self.assertEqual(self.read("IS 1489 (Part 1):1991", 1991, text)["count_in_copy"], 0)

    def test_ocr_damaged_numbers_that_fit_are_accepted(self):
        for text, number, year in [
            ("AMENDMENT NO. 1 JUNE 1999 TO 18 1264:1997 BRASS GRAVITY DIE CASTINGS ( Page 1 )", "IS 1264:1997", 1997),
            ("AMENDMENT NO. 1 JANUARY 1995 TO IS 1203': 1'8' SPENT BLEACHING EARTH (Page 4)", "IS 12039:1986", 1986),
            ("AMENDMENT NO. 1 TO OCTOBER 1987 FOR IS : 3347 ( Part S/Set 2 )- 1979 DIMENSIONS", "IS 3347 (Part 5/Sec 2):1979", 1979),
        ]:
            with self.subTest(text=text[:40]):
                self.assertEqual(self.read(number, year, text)["count_in_copy"], 1)

    def test_mentions_in_running_text_are_not_slips(self):
        text = "(Amendment No. 1) -- Substitute the following. See Amendment No. 3 (1992) issued by IEC."
        self.assertEqual(self.read("IS 2483:1986", 1986, text)["count_in_copy"], 0)

    def test_incorporating_notes_and_ocr_ampersands(self):
        result = self.read("IS 3724:1966", 1966, "Reprint NOVEMBER 1992 ( Incorporating Amendments No. 1 8t 2 )")
        self.assertEqual([a["number"] for a in result["amendments"]], [1, 2])
        self.assertEqual(result["copy_as_of"], 1992)

    def test_a_year_is_not_an_amendment_number(self):
        result = self.read("IS 1853:1961", 1961, "( Incorporating Amendment No. 1982 ,., I)")
        self.assertEqual(result["count_in_copy"], 0)


if __name__ == "__main__":
    unittest.main()
